import datetime as dt
from decimal import Decimal

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.domains.products.models import Product
from app.domains.products.price_observation import PriceObservation
from app.domains.products.retailers import Retailer, RetailerEnum
from app.domains.products.services.price_csv_importer import (
    KauflandPriceCsvParser,
    LidlPriceCsvParser,
    PriceCsvImporter,
)
from app.domains.products.stores import Store


def make_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def make_store(session: Session, store_code: str) -> Store:
    retailer = Retailer(
        id=RetailerEnum.LIDL.value.id,
        name=RetailerEnum.LIDL.value.name,
    )
    session.merge(retailer)
    store = Store(
        retailer_id=RetailerEnum.LIDL.value.id,
        store_code=store_code,
        name=f"Lidl {store_code}",
    )
    session.add(store)
    session.commit()
    session.refresh(store)
    return store


def make_lidl_row(
    *,
    code: str = "0082225",
    name: str = "Krastavac",
    price: str = "1.29",
) -> dict[str, str]:
    return {
        "NAZIV": name,
        "ŠIFRA": code,
        "MARKA": "",
        "NETO_KOLIČINA": "1",
        "JEDINICA_MJERE": "1kg",
        "MALOPRODAJNA_CIJENA": price,
        "CIJENA_ZA_JEDINICU_MJERE": price,
        "MPC_ZA_VRIJEME_POSEBNOG_OBLIKA_PRODAJE": "",
        "BARKOD": "",
        "KATEGORIJA_PROIZVODA": "Hrana",
    }


def make_kaufland_row() -> dict[str, str]:
    return {
        "naziv proizvoda": "Ajax za staklo window & shiny 750 ml",
        "šifra proizvoda": "00010016",
        "marka proizvoda": "Ajax",
        "neto količina(KG)": "0.750",
        "jedinica mjere": "KOM",
        "maloprod.cijena(EUR)": "       2,59",
        "akc.cijena, A=akcija": "A",
        "kol.jed.mj.": "1",
        "jed.mj. (1 KOM/L/KG)": "L",
        "cijena jed.mj.(EUR)": "1,72",
        "MPC poseb.oblik prod": "       1,29",
        "Najniža MPC u 30dana": "2,59",
        "Sidrena cijena": "MPC 2.5.2025=2,59€",
        "barkod": "3838447000195",
        "kategorija proizvoda": "SREDSTVA ZA ČIŠĆENJE",
    }


def test_kaufland_parser_normalizes_tab_delimited_columns():
    normalized = KauflandPriceCsvParser().normalize_row(make_kaufland_row())

    assert normalized is not None
    assert normalized.retailer_product_code == "00010016"
    assert normalized.source_product_name == "Ajax za staklo window & shiny 750 ml"
    assert normalized.barcode == "3838447000195"
    assert normalized.brand == "Ajax"
    assert normalized.net_quantity == "0.750"
    assert normalized.unit_of_measure == "KOM"
    assert normalized.category == "SREDSTVA ZA ČIŠĆENJE"
    assert normalized.price_eur == Decimal("1.29")
    assert normalized.unit_price_eur == Decimal("1.72")
    assert normalized.is_special_sale is True


def test_no_barcode_product_is_reused_by_retailer_product_code_across_stores():
    session = make_session()
    store_a = make_store(session, "209")
    store_b = make_store(session, "269")
    importer = PriceCsvImporter(
        parser=LidlPriceCsvParser(),
        observed_date=dt.date(2026, 4, 29),
    )

    importer.import_prices(session, [make_lidl_row()], store_a)
    importer.import_prices(session, [make_lidl_row(price="1.39")], store_b)

    products = session.exec(select(Product)).all()
    observations = session.exec(select(PriceObservation)).all()

    assert len(products) == 1
    assert products[0].barcode is None
    assert products[0].name == "Krastavac"
    assert len(observations) == 2
    assert {observation.product_id for observation in observations} == {products[0].id}


def test_no_barcode_product_reimport_updates_existing_observation():
    session = make_session()
    store = make_store(session, "209")
    importer = PriceCsvImporter(
        parser=LidlPriceCsvParser(),
        observed_date=dt.date(2026, 4, 29),
    )

    importer.import_prices(session, [make_lidl_row(price="1.29")], store)
    importer.import_prices(session, [make_lidl_row(price="1.49")], store)

    products = session.exec(select(Product)).all()
    observations = session.exec(select(PriceObservation)).all()

    assert len(products) == 1
    assert len(observations) == 1
    assert observations[0].product_id == products[0].id
    assert observations[0].price_eur == Decimal("1.49")
