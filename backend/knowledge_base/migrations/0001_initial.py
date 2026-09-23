from datetime import date

from django.db import migrations, models


VERIFIED = date(2026, 9, 23)


def seed_knowledge(apps, schema_editor):
    Entry = apps.get_model("knowledge_base", "KnowledgeEntry")
    rows = [
        ("payment_individual", ["оплата физическому лицу", "оплата для частного покупателя", "как оплатить"], "Оплата для физического лица доступна по актуальным реквизитам, которые менеджер предоставит при оформлении заказа.", "Жеке тұлға үшін төлем тапсырысты рәсімдеу кезінде менеджер ұсынатын өзекті деректемелер бойынша жүргізіледі.", "approved", "https://ekt.kz/", "sales", "", True),
        ("payment_legal", ["оплата юридическому лицу", "оплата от компании", "безналичная оплата"], "Для юридического лица условия безналичной оплаты и комплект документов уточняются менеджером при оформлении заказа.", "Заңды тұлға үшін қолма-қол ақшасыз төлем және құжаттар шарттарын менеджер нақтылайды.", "approved", "https://ekt.kz/", "sales", "", True),
        ("power_of_attorney", ["доверенность", "получение по доверенности", "нужна ли доверенность"], "Если заказ получает представитель компании, требования к доверенности нужно подтвердить у менеджера до выдачи.", "Тапсырысты компания өкілі алса, сенімхат талаптарын беруге дейін менеджермен нақтылау керек.", "approved_with_qualification", "https://ekt.kz/", "sales", "", True),
        ("delivery_almaty_timing", ["доставка по алматы срок", "сколько идет доставка алматы", "срок доставки"], "Срок доставки по Алматы зависит от наличия и адреса. Точный срок менеджер подтверждает перед оформлением.", "Алматы бойынша жеткізу мерзімі тауардың бар-жоғына және мекенжайға байланысты. Нақты мерзімді менеджер растайды.", "approved_with_qualification", "https://ekt.kz/", "logistics", "", True),
        ("delivery_almaty_free", ["бесплатная доставка алматы", "доставка бесплатно алматы", "когда доставка бесплатная"], "Бесплатная доставка по Алматы зависит от актуальных условий заказа. Подтвердите порог и адрес у менеджера.", "Алматыдағы тегін жеткізу тапсырыстың өзекті шарттарына байланысты. Шекті соманы және мекенжайды менеджерден нақтылаңыз.", "approved_with_qualification", "https://ekt.kz/", "logistics", "", True),
        ("delivery_almaty_paid", ["платная доставка алматы", "стоимость доставки алматы", "доставка за плату"], "Если заказ не подходит под бесплатную доставку, стоимость и способ доставки менеджер рассчитывает по адресу.", "Тапсырыс тегін жеткізуге сәйкес келмесе, құны мен тәсілін менеджер мекенжай бойынша есептейді.", "approved_with_qualification", "https://ekt.kz/", "logistics", "", True),
        ("delivery_regions", ["доставка в регионы", "доставка по казахстану", "доставка в другой город"], "Доставка в регионы возможна по согласованию. Менеджер уточнит перевозчика, срок и стоимость по адресу.", "Өңірлерге жеткізу келісім бойынша мүмкін. Менеджер тасымалдаушыны, мерзімді және құнын мекенжай бойынша нақтылайды.", "approved_with_qualification", "https://ekt.kz/", "logistics", "", True),
        ("pickup", ["самовывоз", "забрать самостоятельно", "где получить заказ"], "Самовывоз доступен при подтверждении готовности заказа и адреса точки менеджером.", "Өзі алып кету тапсырыстың дайындығы мен нүкте мекенжайын менеджер растағаннан кейін қолжетімді.", "approved_with_qualification", "https://ekt.kz/", "logistics", "", True),
        ("minimum_order", ["минимальная партия", "минимальный заказ", "минимальное количество"], "Минимальная партия не подтверждена в базе. Не буду называть неподтверждённую сумму — уточню у менеджера.", "Минималды партия дерекқорда расталмаған. Расталмаған соманы атамаймын — менеджер нақтылайды.", "missing", "https://ekt.kz/", "sales", "minimum-order", False),
        ("minimum_order", ["минимальная партия 15000", "заказ от 15000", "минимальный заказ 15000"], "Минимальная партия — 15 000 ₸.", "Минималды партия — 15 000 ₸.", "conflicted", "https://ekt.kz/", "sales", "minimum-order", False),
        ("minimum_order", ["минимальная партия 30000", "заказ от 30000", "минимальный заказ 30000"], "Минимальная партия — 30 000 ₸.", "Минималды партия — 30 000 ₸.", "conflicted", "https://ekt.kz/personal/cart/", "sales", "minimum-order", False),
    ]
    for intent, variants, answer_ru, answer_kk, status, source_url, owner, conflict_group, published in rows:
        Entry.objects.create(
            intent=intent,
            variants=variants,
            answer_ru=answer_ru,
            answer_kk=answer_kk,
            source_url=source_url,
            verified_at=VERIFIED,
            status=status,
            owner=owner,
            version=1,
            is_current=True,
            published=published,
            conflict_group=conflict_group,
        )


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="KnowledgeEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("intent", models.CharField(max_length=128)),
                ("variants", models.JSONField(default=list)),
                ("answer_ru", models.TextField(blank=True)),
                ("answer_kk", models.TextField(blank=True)),
                ("source_url", models.URLField(max_length=500)),
                ("verified_at", models.DateField(blank=True, null=True)),
                ("status", models.CharField(choices=[("approved", "Approved"), ("approved_with_qualification", "Approved with qualification"), ("conflicted", "Conflicted"), ("missing", "Missing")], max_length=40)),
                ("owner", models.CharField(max_length=128)),
                ("version", models.PositiveIntegerField(default=1)),
                ("is_current", models.BooleanField(default=True)),
                ("published", models.BooleanField(default=True)),
                ("conflict_group", models.CharField(blank=True, max_length=128)),
            ],
            options={"indexes": [models.Index(fields=["intent", "is_current", "published"], name="knowledge_b_intent_8b2f1c_idx"), models.Index(fields=["status", "is_current"], name="knowledge_b_status_0a8a9d_idx")]},
        ),
        migrations.RunPython(seed_knowledge, migrations.RunPython.noop),
    ]
