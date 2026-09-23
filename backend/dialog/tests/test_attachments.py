import io
import json
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from dialog.attachments import extract_attachment


def pdf_file(name="brief.pdf"):
    from pypdf import PdfWriter

    stream = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(stream)
    return SimpleUploadedFile(name, stream.getvalue(), content_type="application/pdf")


def office_file(kind: str, *, macro=False):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types></Types>")
        if kind == "docx":
            archive.writestr("word/document.xml", "<document><p>Кабель 3x2.5</p></document>")
        else:
            archive.writestr("xl/workbook.xml", "<workbook></workbook>")
            archive.writestr("xl/worksheets/sheet1.xml", "<worksheet><c><v>Кабель</v></c></worksheet>")
        if macro:
            archive.writestr("xl/vbaProject.bin", b"not executed")
    content_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if kind == "docx"
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    return SimpleUploadedFile(f"specification.{kind}", stream.getvalue(), content_type=content_type)


def jpeg_file():
    # SOI, one Start-of-Frame marker with 32×16 dimensions, then EOI.
    data = b"\xff\xd8\xff\xc0\x00\x07\x08\x00\x10\x00\x20\xff\xd9"
    return SimpleUploadedFile("photo.jpg", data, content_type="image/jpeg")


class AttachmentApiTests(TestCase):
    def upload(self, uploaded, dialog_id=None):
        data = {"file": uploaded}
        if dialog_id:
            data["dialog_id"] = dialog_id
        return self.client.post("/api/dialog/uploads", data)

    def post_message(self, payload):
        return self.client.post("/api/dialog/messages", data=json.dumps(payload), content_type="application/json")

    def test_uploads_each_supported_format_and_never_exposes_extracted_text(self):
        for factory, expected_format in (
            (pdf_file, "pdf"),
            (lambda: office_file("docx"), "docx"),
            (lambda: office_file("xlsx"), "xlsx"),
            (jpeg_file, "jpeg"),
        ):
            with self.subTest(format=expected_format):
                response = self.upload(factory())
                self.assertEqual(response.status_code, 201, response.content)
                attachment = response.json()["attachment"]
                self.assertEqual(attachment["metadata"]["format"], expected_format)
                self.assertRegex(attachment["id"], r"^[a-f0-9]{32}$")
                self.assertNotIn("text", attachment)

    def test_message_receives_own_session_attachment_and_returns_controlled_receipt(self):
        dialog_id = self.client.get("/api/dialog").json()["dialog_id"]
        attachment = self.upload(office_file("docx"), dialog_id).json()["attachment"]
        response = self.post_message(
            {"dialog_id": dialog_id, "text": "Проверьте спецификацию", "attachment_id": attachment["id"]}
        )
        self.assertEqual(response.status_code, 200)
        message = response.json()["message"]
        self.assertIn("Файл", message["content"])
        self.assertEqual(message["attachment"]["id"], attachment["id"])
        history = self.client.get("/api/dialog").json()["history"]
        self.assertEqual(history[-2]["attachment"]["id"], attachment["id"])
        self.assertNotIn("text", history[-2]["attachment"])

    def test_rejects_invalid_signature_macro_and_foreign_attachment(self):
        bad_pdf = SimpleUploadedFile("bad.pdf", b"not a pdf", content_type="application/pdf")
        self.assertEqual(self.upload(bad_pdf).json()["error"]["code"], "invalid_file_signature")
        wrong_mime = SimpleUploadedFile("photo.jpg", b"%PDF-not-jpeg", content_type="application/pdf")
        self.assertEqual(self.upload(wrong_mime).json()["error"]["code"], "invalid_file_type")
        self.assertEqual(self.upload(office_file("xlsx", macro=True)).json()["error"]["code"], "active_content_not_allowed")

        other = Client()
        attachment_id = other.post("/api/dialog/uploads", {"file": office_file("docx")}).json()["attachment"]["id"]
        response = self.post_message({"text": "Проверьте", "attachment_id": attachment_id})
        self.assertEqual(response.status_code, 400)
        self.assertIn("does not belong", response.json()["error"]["message"])

    def test_rejects_unsafe_archive_and_xml(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as package:
            package.writestr("[Content_Types].xml", "<Types></Types>")
            package.writestr("word/document.xml", "<!DOCTYPE test [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]><document>&xxe;</document>")
        unsafe_xml = SimpleUploadedFile(
            "unsafe.docx",
            archive.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertEqual(self.upload(unsafe_xml).json()["error"]["code"], "unsafe_xml")

        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as package:
            package.writestr("[Content_Types].xml", "<Types></Types>")
            package.writestr("word/document.xml", "A" * 2048)
        compressed = SimpleUploadedFile(
            "compressed.docx",
            archive.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        with self.settings(ATTACHMENT_MAX_COMPRESSION_RATIO=2):
            self.assertEqual(self.upload(compressed).json()["error"]["code"], "unsafe_archive")

    @override_settings(ATTACHMENT_MAX_BYTES=4)
    def test_rejects_oversized_file_after_streaming_copy(self):
        upload = SimpleUploadedFile("large.pdf", b"%PDF-12345", content_type="application/pdf")
        response = self.upload(upload)
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error"]["code"], "attachment_too_large")

    @override_settings(ATTACHMENT_MAX_STORED_PER_DIALOG=1)
    def test_limits_stored_attachments_per_dialog(self):
        self.assertEqual(self.upload(office_file("docx")).status_code, 201)
        response = self.upload(office_file("docx"))
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["error"]["code"], "attachment_limit_exceeded")

    def test_temp_file_is_deleted_after_success_and_rejection(self):
        original = tempfile.NamedTemporaryFile
        with tempfile.TemporaryDirectory() as directory:
            def named_temp_file(**kwargs):
                return original(dir=directory, **kwargs)

            with patch("dialog.attachments.tempfile.NamedTemporaryFile", side_effect=named_temp_file):
                extract_attachment(office_file("docx"))
                with self.assertRaises(ValueError):
                    extract_attachment(SimpleUploadedFile("bad.pdf", b"bad", content_type="application/pdf"))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_retry_and_stream_preserve_attachment(self):
        dialog_id = self.client.get("/api/dialog").json()["dialog_id"]
        attachment = self.upload(office_file("xlsx"), dialog_id).json()["attachment"]
        first = self.post_message({"text": "Проверьте", "dialog_id": dialog_id, "attachment_id": attachment["id"]})
        user_id = next(item["id"] for item in self.client.get("/api/dialog").json()["history"] if item.get("attachment_id") == attachment["id"])
        retry = self.client.post(f"/api/dialog/messages/{user_id}/retry")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(retry.status_code, 200)
        stream = self.client.post(
            "/api/dialog/messages/stream",
            data=json.dumps({"text": "Ещё раз", "dialog_id": dialog_id, "attachment_id": attachment["id"]}),
            content_type="application/json",
        )
        self.assertEqual(stream.status_code, 200)
        body = b"".join(stream.streaming_content).decode()
        self.assertIn(attachment["id"], body)
