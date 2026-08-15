"""Curated device catalogue used by the Device Models admin registry.

The importer is deliberately additive.  Existing retailer-specific entries are
never removed; matching entries are simply reactivated and missing variants are
added once.
"""

from django.db import transaction
from django.utils.text import slugify
import re

from .models import (
    PhoneBrand,
    PhoneColorOption,
    PhoneModel,
    PhoneModelVariant,
    PhonePlatform,
    PhoneRamOption,
    PhoneStorageOption,
    Product,
)


PHONE = {
    "Apple": [
        "iPhone 17e",
        "iPhone 16e", "iPhone 16", "iPhone 16 Plus", "iPhone 16 Pro", "iPhone 16 Pro Max",
        "iPhone 15", "iPhone 15 Plus", "iPhone 15 Pro", "iPhone 15 Pro Max",
        "iPhone 14", "iPhone 14 Plus", "iPhone 14 Pro", "iPhone 14 Pro Max",
        "iPhone 13", "iPhone 13 mini", "iPhone 13 Pro", "iPhone 13 Pro Max",
        "iPhone 12", "iPhone 12 mini", "iPhone 12 Pro", "iPhone 12 Pro Max",
        "iPhone 11", "iPhone 11 Pro", "iPhone 11 Pro Max", "iPhone XS", "iPhone XS Max",
        "iPhone XR", "iPhone X", "iPhone 8", "iPhone 8 Plus", "iPhone 7", "iPhone 7 Plus",
        "iPhone 6", "iPhone 6 Plus", "iPhone 5s", "iPhone 5c", "iPhone 5", "iPhone 4s", "iPhone 4", "iPhone 3GS", "iPhone 3G", "iPhone (1st generation)",
        "iPhone SE (3rd generation)", "iPhone SE (2nd generation)", "iPhone 6s", "iPhone 6s Plus",
    ],
    "Sony Ericsson": ["T610", "K750i", "W800", "W810", "W580", "P990", "P1", "Xperia X10", "Xperia X10 mini", "Xperia Arc", "Xperia Ray", "Xperia Play", "Xperia Neo", "Xperia S", "Xperia T", "Xperia V", "Xperia Z", "Xperia Z1", "Xperia Z2", "Xperia Z3", "Xperia M2", "Xperia C", "Xperia E"],
    "HTC": ["Dream", "Magic", "Hero", "Desire", "Desire HD", "One X", "One M7", "One M8", "One M9", "10", "U11", "U12+", "Wildfire X"],
    "BlackBerry": ["Pearl", "Curve 8520", "Bold 9900", "Torch 9810", "Z10", "Q10", "Z30", "Passport", "Classic", "Priv", "DTEK60", "KEYone", "KEY2"],
    "LG": ["Optimus One", "Optimus G", "G2", "G3", "G4", "G5", "G6", "V10", "V20", "V30", "V40 ThinQ", "V50 ThinQ", "Wing", "Velvet"],
    "Microsoft": ["Lumia 535", "Lumia 640", "Lumia 650", "Lumia 730", "Lumia 830", "Lumia 930", "Lumia 950", "Lumia 950 XL", "Surface Duo 2"],
    "Palm": ["Treo 650", "Treo 750", "Pre", "Pre 2", "Pre 3", "Pixi"],
    "Alcatel": ["OT-800", "One Touch Idol", "Idol 3", "Idol 4", "3V", "5V", "1S"],
    "Siemens": ["S10", "SL45", "SX1", "A50", "M55"],
    "Samsung": ["Galaxy S26", "Galaxy S26+", "Galaxy S26 Ultra", "Galaxy S25", "Galaxy S25 Ultra", "Galaxy S24", "Galaxy S24 Ultra", "Galaxy S23", "Galaxy S22", "Galaxy S21", "Galaxy S20", "Galaxy S10", "Galaxy S9", "Galaxy S8", "Galaxy S7", "Galaxy S6", "Galaxy S5", "Galaxy S4", "Galaxy S3", "Galaxy S2", "Galaxy S", "Galaxy Note 20", "Galaxy Note 10", "Galaxy Note 9", "Galaxy Note 8", "Galaxy Note 5", "Galaxy Z Fold6", "Galaxy Z Flip6", "Galaxy A55", "Galaxy A35", "Galaxy A14", "Galaxy M55", "Galaxy J7", "Galaxy J5"],
    "Google": ["Pixel 9", "Pixel 9 Pro", "Pixel 9 Pro XL", "Pixel 8a", "Pixel 8", "Pixel 7", "Pixel 6", "Pixel 5", "Pixel 4", "Pixel 3", "Pixel 2", "Pixel", "Pixel Fold", "Nexus 6P", "Nexus 5X", "Nexus 5", "Nexus 4", "Nexus 7"],
    "OnePlus": ["OnePlus 13", "OnePlus 12", "OnePlus 12R", "OnePlus Open", "Nord 4", "Nord CE4"],
    "Xiaomi": ["Xiaomi 15", "Xiaomi 14", "Xiaomi 14 Ultra", "Xiaomi 14T", "Mi 13"],
    "Redmi": ["Redmi Note 14 Pro+", "Redmi Note 14 Pro", "Redmi Note 13", "Redmi 13", "Redmi K80"],
    "POCO": ["POCO F6 Pro", "POCO F6", "POCO X6 Pro", "POCO X6", "POCO M6 Pro"],
    "Motorola": ["Edge 50 Ultra", "Edge 50 Pro", "Razr 50 Ultra", "Razr 50", "Moto G85", "Moto G75"],
    "OPPO": ["Find X8 Pro", "Find X8", "Reno 12 Pro", "Reno 12", "A3 Pro"],
    "vivo": ["X200 Pro", "X100 Pro", "V40 Pro", "V40", "Y200 Pro"],
    "realme": ["GT 7 Pro", "GT 6", "12 Pro+", "12 Pro", "Narzo 70 Pro"],
    "Honor": ["Magic7 Pro", "Magic V3", "200 Pro", "X8c", "90"],
    "Huawei": ["Pura 70 Pro", "Mate 70 Pro", "Mate X6", "Nova 13 Pro", "P60 Pro"],
    "Sony": ["Xperia 1 VI", "Xperia 5 V", "Xperia 10 VI", "Xperia Pro-I"],
    "Nokia": ["Nokia 3310", "Nokia 1100", "Nokia 6600", "Nokia N95", "Nokia N97", "Nokia E71", "Nokia Lumia 520", "Nokia Lumia 920", "Nokia Lumia 1020", "Nokia 6", "Nokia 7 Plus", "Nokia 8", "Nokia 9 PureView", "Nokia X30", "Nokia G42", "Nokia C32", "Nokia 8.3 5G"],
    "ASUS": ["ROG Phone 9", "ROG Phone 8", "Zenfone 11 Ultra", "Zenfone 10"],
    "Nothing": ["Phone (3)", "Phone (2a)", "Phone (2)", "CMF Phone 1"],
    "ZTE": ["nubia Z70 Ultra", "nubia RedMagic 10 Pro", "Axon 60 Ultra"],
    "Lenovo": ["Legion Phone Duel 2", "K14", "ThinkPhone by Motorola"],
    "Fairphone": ["Fairphone 5", "Fairphone 4"],
    "TCL": ["TCL 50 XL", "TCL 40 X", "TCL 30 5G"],
    "Infinix": ["Zero 40", "GT 30 Pro", "Note 40 Pro", "Hot 50 Pro"],
    "Tecno": ["Phantom V Fold2", "Phantom V Flip2", "Camon 30 Pro", "Pova 6 Pro"],
}

TABLETS = {
    "Apple": ["iPad Pro 13-inch (M4)", "iPad Pro 11-inch (M4)", "iPad Air 13-inch (M4)", "iPad Air 11-inch (M4)", "iPad Air 13-inch (M2)", "iPad Air 11-inch (M2)", "iPad (10th generation)", "iPad mini (6th generation)"],
    "Samsung": ["Galaxy Tab S10 Ultra", "Galaxy Tab S10+", "Galaxy Tab S9 Ultra", "Galaxy Tab S9 FE", "Galaxy Tab A9+", "Galaxy Tab Active5"],
    "Lenovo": ["Yoga Tab Plus", "Tab P12", "Tab P11 Pro Gen 2", "Tab M11", "Legion Tab"],
    "Microsoft": ["Surface Pro 11", "Surface Pro 10", "Surface Go 4", "Surface Duo 2"],
    "Google": ["Pixel Tablet"],
    "OnePlus": ["OnePlus Pad 2", "OnePlus Pad Go"],
    "Xiaomi": ["Xiaomi Pad 7 Pro", "Xiaomi Pad 7", "Xiaomi Pad 6S Pro", "Redmi Pad Pro", "Redmi Pad SE"],
    "Huawei": ["MatePad Pro 13.2", "MatePad 12 X", "MatePad Air", "MatePad SE"],
    "Amazon": ["Fire Max 11", "Fire HD 10", "Fire HD 8", "Fire 7"],
    "HONOR": ["MagicPad 2", "Pad 9", "Pad X9"],
    "TCL": ["NxtPaper 14", "Tab 10 NXTPAPER", "Tab 11 FE"],
    "Nokia": ["T20", "T10"],
    "ASUS": ["ROG Flow Z13", "Transformer Mini"],
    "Acer": ["Chromebook Tab 510"],
}

LAPTOPS = {
    "Apple": ["MacBook Neo", "MacBook Pro 14-inch (M5 Pro)", "MacBook Pro 16-inch (M5 Pro)", "MacBook Pro 14-inch (M5 Max)", "MacBook Pro 16-inch (M5 Max)", "MacBook Air 13-inch (M4)", "MacBook Air 15-inch (M4)", "MacBook Pro 14-inch (M4)", "MacBook Pro 16-inch (M4)", "MacBook Air 13-inch (M3)"],
    "Dell": ["XPS 13", "XPS 14", "XPS 16", "Inspiron 14", "Inspiron 16", "Latitude 7450", "Precision 5690", "Alienware m16"],
    "HP": ["Spectre x360 14", "Envy x360 14", "Pavilion Plus 14", "Pavilion 15", "EliteBook 840", "ProBook 450", "Omen 16", "Victus 16"],
    "Lenovo": ["ThinkPad X1 Carbon Gen 12", "ThinkPad T14 Gen 5", "Yoga 9i", "Yoga Slim 7i", "IdeaPad Slim 5", "Legion Pro 7i", "LOQ 15"],
    "ASUS": ["Zenbook A16", "Zenbook S 16", "Zenbook 14 OLED", "Vivobook S 15", "ROG Zephyrus G16", "ROG Strix G18", "TUF Gaming A15", "ExpertBook B9"],
    "Acer": ["Swift Go 14", "Swift X 14", "Aspire 5", "Spin 5", "Predator Helios 16", "Nitro V 15", "Chromebook Plus 515"],
    "Microsoft": ["Surface Laptop 8th Edition", "Surface Pro 8th Edition", "Surface Laptop 7", "Surface Laptop Studio 2", "Surface Laptop Go 3"],
    "Samsung": ["Galaxy Book5 Pro", "Galaxy Book4 Edge", "Galaxy Book4 Pro", "Galaxy Book4 360"],
    "LG": ["LG gram 16 (2026)", "LG gram 17 (2026)", "LG gram Pro 16 (2026)", "LG gram 16", "LG gram 17", "LG gram Pro 16"],
    "MSI": ["Prestige 16 AI Evo", "Stealth 16 AI Studio", "Creator Z16", "Raider 18 HX", "Katana 15"],
    "Razer": ["Blade 16 (2026)", "Blade 16", "Blade 14", "Blade 18"],
    "Huawei": ["MateBook X Pro", "MateBook 14", "MateBook D 16"],
    "Xiaomi": ["RedmiBook Pro 16", "Xiaomi Book Pro 14"],
    "Framework": ["Framework Laptop 16", "Framework Laptop 13"],
    "Google": ["Pixelbook Go", "Pixelbook"],
    "Chuwi": ["CoreBook X", "GemiBook Plus"],
    "Panasonic": ["Toughbook 55", "Toughbook 40"],
}

COLOURS = {
    "Black": "#111827", "White": "#f8fafc", "Silver": "#cbd5e1", "Blue": "#2563eb",
    "Green": "#16a34a", "Red": "#dc2626", "Gold": "#eab308", "Purple": "#9333ea",
    "Pink": "#ec4899", "Graphite": "#475569", "Natural Titanium": "#a8a29e",
}


def _unique_slug(model, value, lookup):
    base = slugify(value) or "device"
    candidate = base
    n = 2
    manager = lookup.objects
    while manager.filter(slug=candidate).exclude(pk=getattr(model, "pk", None)).exists():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def _variants_for(family, brand, model_name):
    if family == "laptop":
        rams, storage = ["8GB", "16GB", "32GB"], ["256GB", "512GB", "1TB"]
    elif family == "android":
        rams, storage = ["4GB", "8GB", "12GB"], ["64GB", "128GB", "256GB"]
    else:
        rams, storage = ["6GB", "8GB", "12GB"], ["128GB", "256GB", "512GB"]
    if brand == "Apple":
        rams = ["8GB", "16GB"] if family == "laptop" else ["4GB", "8GB"]
    colours = ["Black", "Silver", "Blue", "Red", "Green", "Gold"]
    return [
        (rams[0], storage[0], colours[0]),
        (rams[0], storage[min(1, len(storage) - 1)], colours[1]),
        (rams[1], storage[min(1, len(storage) - 1)], colours[2]),
        (rams[1], storage[-1], colours[3]),
        (rams[-1], storage[-1], colours[4]),
        (rams[-1], storage[-1], colours[5]),
    ]


@transaction.atomic
def seed_device_catalog():
    families = {"apple": PHONE, "android": TABLETS, "laptop": LAPTOPS}
    stats = {"platforms": 0, "brands": 0, "models": 0, "variants": 0}
    for family, brand_map in families.items():
        platform, created = PhonePlatform.objects.get_or_create(name=family, defaults={"is_active": True})
        if created:
            stats["platforms"] += 1
        if not platform.is_active:
            platform.is_active = True
            platform.save(update_fields=["is_active", "updated_at"])
        for brand_index, (brand_name, model_names) in enumerate(brand_map.items(), start=1):
            brand = PhoneBrand.objects.filter(platform=platform, name__iexact=brand_name).first()
            if not brand:
                brand = PhoneBrand.objects.create(platform=platform, name=brand_name, slug=_unique_slug(None, brand_name, PhoneBrand), sort_order=brand_index)
                stats["brands"] += 1
            elif not brand.is_active:
                brand.is_active = True
                brand.save(update_fields=["is_active", "updated_at"])
            for model_index, model_name in enumerate(model_names, start=1):
                model = PhoneModel.objects.filter(platform=platform, brand=brand, name__iexact=model_name).first()
                if not model:
                    model = PhoneModel.objects.create(platform=platform, brand=brand, name=model_name, slug=_unique_slug(None, f"{brand_name}-{model_name}", PhoneModel), sort_order=model_index)
                    stats["models"] += 1
                elif not model.is_active:
                    model.is_active = True
                    model.save(update_fields=["is_active", "updated_at"])
                for variant_index, (ram, storage, colour) in enumerate(_variants_for(family, brand_name, model_name), start=1):
                    PhoneRamOption.objects.get_or_create(label=ram, defaults={"sort_order": variant_index})
                    PhoneStorageOption.objects.get_or_create(label=storage, defaults={"sort_order": variant_index})
                    PhoneColorOption.objects.get_or_create(name=colour, defaults={"color_hex": COLOURS[colour], "sort_order": variant_index})
                    variant, created = PhoneModelVariant.objects.get_or_create(
                        phone_model=model, ram=ram, storage=storage, color=colour,
                        defaults={"color_hex": COLOURS[colour], "sort_order": variant_index, "is_active": True},
                    )
                    if created:
                        stats["variants"] += 1
                    elif not variant.is_active:
                        variant.is_active = True
                        variant.save(update_fields=["is_active", "updated_at"])
    return stats


@transaction.atomic
def sync_catalog_payload(payload):
    """Merge a JSON device feed into the registry.

    Feed shape: ``{"phone": {"Brand": ["Model"]}, "tablet": ...}``.
    A model may also be ``{"name": "...", "variants": [{"ram": ..., 
    "storage": ..., "color": ..., "color_hex": ...}]}``. The merge is
    additive and case-insensitive.
    """
    family_aliases = {"phone": "apple", "phones": "apple", "apple": "apple", "tablet": "android", "tablets": "android", "android": "android", "laptop": "laptop", "laptops": "laptop"}
    stats = {"brands": 0, "models": 0, "variants": 0}
    for family_key, brands in (payload or {}).items():
        family = family_aliases.get(str(family_key).lower())
        if not family or not isinstance(brands, dict):
            continue
        platform, _ = PhonePlatform.objects.get_or_create(name=family, defaults={"is_active": True})
        for brand_name, raw_models in brands.items():
            brand_name = str(brand_name).strip()
            if not brand_name or not isinstance(raw_models, list):
                continue
            brand = PhoneBrand.objects.filter(platform=platform, name__iexact=brand_name).first()
            if not brand:
                brand = PhoneBrand.objects.create(platform=platform, name=brand_name, slug=_unique_slug(None, brand_name, PhoneBrand))
                stats["brands"] += 1
            elif not brand.is_active:
                brand.is_active = True
                brand.save(update_fields=["is_active", "updated_at"])
            for raw_model in raw_models:
                if isinstance(raw_model, str):
                    model_name, feed_variants, feed_year = raw_model.strip(), [], None
                elif isinstance(raw_model, dict):
                    model_name = str(raw_model.get("name", "")).strip()
                    feed_variants = raw_model.get("variants") or []
                    try:
                        feed_year = int(raw_model.get("released_year")) if raw_model.get("released_year") else None
                    except (TypeError, ValueError):
                        feed_year = None
                else:
                    continue
                if not model_name:
                    continue
                model = PhoneModel.objects.filter(platform=platform, brand=brand, name__iexact=model_name).first()
                if not model:
                    model = PhoneModel.objects.create(platform=platform, brand=brand, name=model_name, released_year=feed_year, slug=_unique_slug(None, f"{brand_name}-{model_name}", PhoneModel))
                    stats["models"] += 1
                elif feed_year and model.released_year != feed_year:
                    model.released_year = feed_year
                    model.save(update_fields=["released_year", "updated_at"])
                for item in feed_variants:
                    if not isinstance(item, dict):
                        continue
                    ram, storage, color = str(item.get("ram", "")).strip(), str(item.get("storage", "")).strip(), str(item.get("color", "")).strip()
                    if not (ram or storage or color):
                        continue
                    variant = PhoneModelVariant.objects.filter(phone_model=model, ram__iexact=ram, storage__iexact=storage, color__iexact=color).first()
                    if not variant:
                        PhoneModelVariant.objects.create(phone_model=model, ram=ram, storage=storage, color=color, color_hex=str(item.get("color_hex", "")).strip())
                        stats["variants"] += 1
    return stats


@transaction.atomic
def rebuild_device_options_and_variants():
    """Rebuild global option masters from every device model's variants.

    This also fills older/custom models which predate the preset catalogue.
    Existing variants are preserved; only missing combinations are added.
    """
    stats = {"models_checked": 0, "variants_added": 0, "ram_options": 0, "storage_options": 0, "colour_options": 0}
    for model in PhoneModel.objects.select_related("platform", "brand").all():
        stats["models_checked"] += 1
        family = model.platform.name
        brand_name = model.brand.name if model.brand else ""
        existing = set(
            (v.ram.strip().lower(), v.storage.strip().lower(), v.color.strip().lower())
            for v in model.variants.all()
        )
        for ram, storage, colour in _variants_for(family, brand_name, model.name):
            key = (ram.lower(), storage.lower(), colour.lower())
            if key in existing:
                continue
            PhoneModelVariant.objects.create(
                phone_model=model,
                ram=ram,
                storage=storage,
                color=colour,
                color_hex=COLOURS[colour],
                sort_order=len(existing) + 1,
            )
            existing.add(key)
            stats["variants_added"] += 1

    # These tables are master lists only; variants store their values directly.
    # Replacing them prevents stale/orphaned options from appearing in Admin.
    PhoneRamOption.objects.all().delete()
    PhoneStorageOption.objects.all().delete()
    PhoneColorOption.objects.all().delete()

    def canonical_values(values):
        unique = {}
        for raw in values:
            value = raw.strip()
            if not value:
                continue
            # Treat cosmetic spacing/case differences as the same option.
            key = "".join(value.lower().split())
            current = unique.get(key)
            if current is None or (" " in current and " " not in value):
                unique[key] = value
        return sorted(unique.values(), key=lambda x: (len(x), x.lower()))

    ram_values = canonical_values(v.ram for v in PhoneModelVariant.objects.filter(is_active=True))
    storage_values = canonical_values(v.storage for v in PhoneModelVariant.objects.filter(is_active=True))
    colour_values = {}
    for variant in PhoneModelVariant.objects.filter(is_active=True).exclude(color=""):
        colour_values.setdefault(variant.color.strip(), variant.color_hex or COLOURS.get(variant.color.strip(), ""))

    PhoneRamOption.objects.bulk_create([PhoneRamOption(label=value, sort_order=index) for index, value in enumerate(ram_values, 1)])
    PhoneStorageOption.objects.bulk_create([PhoneStorageOption(label=value, sort_order=index) for index, value in enumerate(storage_values, 1)])
    PhoneColorOption.objects.bulk_create([PhoneColorOption(name=name, color_hex=color, sort_order=index) for index, (name, color) in enumerate(sorted(colour_values.items()), 1)])
    stats["ram_options"] = len(ram_values)
    stats["storage_options"] = len(storage_values)
    stats["colour_options"] = len(colour_values)
    return stats


def infer_device_model_year(model):
    """Infer a practical release year from common device generations."""
    text = f"{model.brand.name if model.brand else ''} {model.name}".lower()
    explicit = re.search(r"\b(20(?:1[8-9]|2[0-6]))\b", text)
    if explicit:
        return int(explicit.group(1))
    # Product families whose generation number maps directly to the release year.
    direct = [
        (r"sony ericsson.*t610", 2003),
        (r"sony ericsson.*(k750|w800)", 2005),
        (r"sony ericsson.*w810|sony ericsson.*p990", 2006),
        (r"sony ericsson.*(w580|p1)", 2007),
        (r"sony ericsson.*xperia x10", 2010),
        (r"sony ericsson.*(arc|ray|play|neo)", 2011),
        (r"sony ericsson.*(xperia s|xperia t|xperia v|xperia c)", 2012),
        (r"sony ericsson.*xperia z1|sony ericsson.*xperia z", 2013),
        (r"sony ericsson.*(xperia z2|xperia m2)", 2014),
        (r"sony ericsson.*xperia z3", 2014),
        (r"htc.*dream|htc.*magic", 2009),
        (r"htc.*hero", 2009),
        (r"htc.*desire", 2010),
        (r"blackberry.*(pearl|curve)", 2008),
        (r"blackberry.*bold", 2008),
        (r"blackberry.*(torch|z10|q10)", 2013),
        (r"blackberry.*(passport|classic|priv)", 2015),
        (r"nokia.*1100", 2003),
        (r"nokia.*3310", 2000),
        (r"nokia.*6600|nokia.*n95", 2007),
        (r"nokia.*e71|nokia.*n97", 2009),
        (r"iphone\s*17e|galaxy\s*s26|macbook\s*neo|m5\s*(pro|max)|surface\s*(laptop|pro)\s*8th|zenbook\s*a16|gram.*2026|blade\s*16.*2026|ipad\s*air.*m4", 2026),
        (r"iphone\s*16e", 2025),
        (r"iphone\s*16|galaxy\s*s25|pixel\s*9|oneplus\s*13|xiaomi\s*15|edge\s*50|razr\s*50|find\s*x8|reno\s*12|x200|v40|gt\s*7|magic7|magic\s*v3|pura\s*70|phantom\s*v(fold2|flip2)", 2024),
        (r"iphone\s*15", 2023),
        (r"galaxy\s*s24|pixel\s*8|oneplus\s*12|xiaomi\s*14|pixel\s*tablet|ipad\s*(pro|air).*m4|ipad.*10th|tab\s*s10|surface\s*pro\s*11|surface\s*laptop\s*7|macbook.*m4|zenbook\s*s\s*16|swift\s*go\s*14", 2024),
        (r"galaxy\s*s23|pixel\s*7|oneplus\s*11|xiaomi\s*13|ipad.*6th|macbook.*m3|surface\s*pro\s*10|tab\s*s9|thinkpad.*gen\s*12", 2023),
        (r"galaxy\s*s22|pixel\s*6|oneplus\s*10|ipad.*9th|tab\s*s8|surface\s*pro\s*9", 2022),
        (r"galaxy\s*s21|pixel\s*5|ipad.*8th|tab\s*s7", 2021),
        (r"iphone\s*14", 2022),
        (r"iphone\s*13", 2021),
        (r"iphone\s*12", 2020),
        (r"iphone\s*se.*3rd", 2022),
        (r"iphone\s*se.*2nd", 2020),
        (r"iphone\s*11", 2019),
        (r"iphone\s*(xs|xr|x)", 2018),
        (r"iphone\s*8|iphone\s*7", 2017),
        (r"iphone\s*6s", 2015),
        (r"iphone\s*6", 2014),
        (r"iphone\s*(5s|5c|5)", 2013),
        (r"iphone\s*4s", 2011),
        (r"iphone\s*4", 2010),
        (r"iphone\s*3gs", 2009),
        (r"iphone\s*3g", 2008),
        (r"iphone.*1st|iphone\s*original", 2007),
    ]
    for pattern, year in direct:
        if re.search(pattern, text):
            return year
    # A named generation is usually enough to give an accurate catalogue year.
    if re.search(r"gen\s*2|2nd|ii|2023", text):
        return 2023
    if re.search(r"gen\s*3|3rd|iii", text):
        return 2022
    return 2024


@transaction.atomic
def backfill_device_model_years():
    updated = 0
    for model in PhoneModel.objects.select_related("brand").all():
        inferred_year = infer_device_model_year(model)
        if model.released_year != inferred_year:
            model.released_year = inferred_year
            model.save(update_fields=["released_year", "updated_at"])
            updated += 1
    return {"models_updated": updated}


@transaction.atomic
def merge_iphone_brand_into_apple():
    """Move the legacy iPhone brand into Apple and merge duplicate models safely."""
    platform = PhonePlatform.objects.get(name="apple")
    apple, _ = PhoneBrand.objects.get_or_create(platform=platform, name="Apple", defaults={"slug": _unique_slug(None, "Apple", PhoneBrand), "is_active": True})
    source = PhoneBrand.objects.filter(platform=platform, name__iexact="iPhone").exclude(pk=apple.pk).first()
    if not source:
        return {"models_moved": 0, "models_merged": 0, "variants_moved": 0, "brand_removed": False}
    moved = merged = variants_moved = 0
    for source_model in PhoneModel.objects.filter(brand=source):
        target = PhoneModel.objects.filter(platform=platform, brand=apple, name__iexact=source_model.name).exclude(pk=source_model.pk).first()
        if not target:
            source_model.brand = apple
            source_model.save(update_fields=["brand", "updated_at"])
            moved += 1
            continue
        for source_variant in source_model.variants.all():
            target_variant = target.variants.filter(
                ram__iexact=source_variant.ram,
                storage__iexact=source_variant.storage,
                color__iexact=source_variant.color,
            ).first()
            if target_variant:
                Product.objects.filter(phone_variant=source_variant).update(phone_variant=target_variant)
                source_variant.is_active = False
                source_variant.save(update_fields=["is_active", "updated_at"])
            else:
                source_variant.phone_model = target
                source_variant.save(update_fields=["phone_model", "updated_at"])
                variants_moved += 1
        source_model.is_active = False
        source_model.save(update_fields=["is_active", "updated_at"])
        merged += 1
    source.is_active = False
    source.save(update_fields=["is_active", "updated_at"])
    return {"models_moved": moved, "models_merged": merged, "variants_moved": variants_moved, "brand_removed": True}
