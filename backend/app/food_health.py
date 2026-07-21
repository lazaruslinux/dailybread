"""The barcode health-check rule engine: pure functions over a food's label
data, no database and no network. Given a food (its ingredient text, additive
tags, NOVA class, and per-100 nutrition) it returns a verdict tier and a list of
plain-language flags.

The rules are deliberately simple and transparent, not a nutrition science
model: substring/word matching over the lowercased ingredient list (no negation
or context handling), a handful of per-serving nutrient thresholds, and the
NOVA processing class. Every term that names an oil names it explicitly, so
olive/avocado/coconut oil and sunflower lecithin can never trip the seed-oil
rule. Flags carry a category so a text hit and an additive-tag hit for the same
concern collapse to one line.

Verdict tiers:
  whole    no concerns and NOVA says whole/minimally processed
  clean    no concerns, with an ingredient list to judge by
  mixed    at least one concern (a single "bad", or warnings)
  poor     two or more "bad" concerns, or any hydrogenated oil
  unknown  nothing to judge by (no ingredients, additives, or NOVA)
"""

import dataclasses
import re

# ---- flags ---------------------------------------------------------------------


@dataclasses.dataclass
class Flag:
    category: str
    severity: str  # "bad" | "warn" | "info"
    label: str
    detail: str


@dataclasses.dataclass
class Assessment:
    verdict: str
    flags: list[Flag]


_SEVERITY_ORDER = {"bad": 0, "warn": 1, "info": 2}


# ---- ingredient-term rules -----------------------------------------------------
# Each rule: a category, a severity, a user-facing label + detail, and the terms
# that trigger it. A term matches on a letter/digit boundary (so "sunflower oil"
# never fires on "sunflower lecithin", and "blue 1" never fires on "blue 12"),
# with internal spaces allowed to be any whitespace run.


@dataclasses.dataclass
class _Rule:
    category: str
    severity: str
    label: str
    detail: str
    terms: tuple[str, ...]


_RULES: tuple[_Rule, ...] = (
    _Rule(
        "seed_oil",
        "bad",
        "Seed oils",
        "Contains industrial seed oils (for example soybean, canola, or corn oil).",
        (
            "soybean oil",
            "soy oil",
            "soya oil",
            "canola oil",
            "rapeseed oil",
            "corn oil",
            "cottonseed oil",
            "sunflower oil",
            "safflower oil",
            "grapeseed oil",
            "grape seed oil",
            "rice bran oil",
            "vegetable oil",
            "vegetable shortening",
        ),
    ),
    _Rule(
        "hydrogenated",
        "bad",
        "Hydrogenated oil",
        "Contains hydrogenated oil, a source of artificial trans fat.",
        ("hydrogenated",),
    ),
    _Rule(
        "sweetener",
        "bad",
        "Artificial sweetener",
        "Contains artificial sweeteners (for example aspartame, sucralose, "
        "or acesulfame).",
        (
            "aspartame",
            "sucralose",
            "acesulfame",
            "saccharin",
            "neotame",
            "advantame",
            "cyclamate",
        ),
    ),
    _Rule(
        "sugar_alcohol",
        "warn",
        "Sugar alcohol",
        "Contains sugar alcohols, which can upset digestion in larger amounts.",
        (
            "sorbitol",
            "xylitol",
            "maltitol",
            "erythritol",
            "mannitol",
            "isomalt",
            "lactitol",
        ),
    ),
    _Rule(
        "dye",
        "bad",
        "Artificial coloring",
        "Contains artificial food dyes.",
        (
            "red 40",
            "red 3",
            "yellow 5",
            "yellow 6",
            "blue 1",
            "blue 2",
            "green 3",
            "tartrazine",
            "allura red",
            "erythrosine",
            "sunset yellow",
            "brilliant blue",
        ),
    ),
    _Rule(
        "dye_warn",
        "warn",
        "Added coloring",
        "Contains added coloring such as caramel color or titanium dioxide.",
        ("caramel color", "caramel colour", "titanium dioxide"),
    ),
    _Rule(
        "preservative",
        "bad",
        "Preservative of concern",
        "Contains preservatives such as BHA, BHT, TBHQ, or nitrites.",
        (
            "bha",
            "bht",
            "tbhq",
            "nitrite",
            "nitrites",
            "nitrate",
            "nitrates",
            "propylparaben",
            "propyl paraben",
        ),
    ),
    _Rule(
        "preservative_warn",
        "warn",
        "Preservative",
        "Contains preservatives such as benzoates, sorbates, or sulfites.",
        (
            "benzoate",
            "sorbate",
            "sulfite",
            "sulfites",
            "sulphite",
            "sulphites",
            "edta",
            "natamycin",
        ),
    ),
)


# Aliases for added sugar, used only as a fallback when the food carries no
# added-sugar nutrient: their presence flags added sugar without a quantity.
_ADDED_SUGAR_TERMS: tuple[str, ...] = (
    "sugar",
    "high fructose corn syrup",
    "corn syrup",
    "cane sugar",
    "cane syrup",
    "brown sugar",
    "invert sugar",
    "dextrose",
    "fructose",
    "sucrose",
    "maltose",
    "glucose syrup",
    "malt syrup",
    "molasses",
    "honey",
    "agave",
    "fruit juice concentrate",
)


def _compile(term: str) -> re.Pattern:
    # spaces -> any whitespace run; letter/digit boundaries either side. A "non "
    # right before the term advertises its absence ("non-hydrogenated palm
    # shortening") and must not flag.
    body = r"\s+".join(re.escape(part) for part in term.split(" "))
    return re.compile(r"(?<!non\s)(?<![a-z0-9])" + body + r"(?![a-z0-9])")


_RULE_PATTERNS: tuple[tuple[_Rule, tuple[re.Pattern, ...]], ...] = tuple(
    (rule, tuple(_compile(t) for t in rule.terms)) for rule in _RULES
)
_ADDED_SUGAR_PATTERNS: tuple[re.Pattern, ...] = tuple(
    _compile(t) for t in _ADDED_SUGAR_TERMS
)


def _normalize(text: str) -> str:
    """Lowercase and flatten every non-alphanumeric run to a single space, so a
    label's punctuation ("Red #40", "acesulfame-K", "sugar.") doesn't hide a
    term. Word/number boundaries then fall on the spaces."""
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower())


def _text_hit(patterns: tuple[re.Pattern, ...], haystack: str) -> bool:
    return any(p.search(haystack) for p in patterns)


_INGREDIENT_SEPARATORS = re.compile(
    r"[,;\n，،]|\band\b", re.IGNORECASE
)


def _sole_ingredient(text: str) -> str | None:
    """The single ingredient an ingredient list names, or None when it names
    more than one. Ignores a trailing period ("HONEY.") and any parenthesized
    qualifiers ("Honey (raw, unfiltered)"); a comma, semicolon, newline, the
    word "and", or a unicode comma all mark more than one ingredient. Returns
    the paren-stripped body so callers judge the ingredient itself, not its
    parenthesized sub-ingredients ("Milk chocolate (sugar, cocoa butter)" must
    not read as sugar)."""
    body = re.sub(r"\([^)]*\)", " ", text or "").strip().rstrip(".")
    if not body or _INGREDIENT_SEPARATORS.search(body) is not None:
        return None
    return body


# ---- additive e-number tags ----------------------------------------------------
# Open Food Facts reports additives as "en:eNNN" tags. Map the ones we care about
# to the same categories the text rules use, so a tag hit and a text hit collapse.


def _additive_map() -> dict[str, str]:
    m: dict[str, str] = {}
    dyes = (
        "e102", "e104", "e110", "e122", "e124", "e127", "e129",
        "e131", "e132", "e133", "e142", "e143", "e151", "e155",
    )
    for e in dyes:
        m[e] = "dye"
    for e in ("e150", "e150a", "e150b", "e150c", "e150d", "e171"):
        m[e] = "dye_warn"
    for e in ("e319", "e320", "e321", "e249", "e250", "e251", "e252"):
        m[e] = "preservative"
    warn_pres = ["e200", "e202", "e203", "e210", "e211", "e212", "e213",
                 "e235", "e385"]
    warn_pres += [f"e{n}" for n in range(220, 229)]  # sulfites e220-e228
    for e in warn_pres:
        m[e] = "preservative_warn"
    for e in ("e950", "e951", "e952", "e954", "e955", "e961", "e962"):
        m[e] = "sweetener"
    for e in ("e420", "e421", "e953", "e965", "e966", "e967", "e968"):
        m[e] = "sugar_alcohol"
    return m


_ADDITIVE_FLAGS: dict[str, str] = _additive_map()
_RULE_BY_CATEGORY: dict[str, _Rule] = {r.category: r for r in _RULES}


def _additive_categories(additives: str) -> set[str]:
    """The concern categories present in a comma-joined OFF additives tag list."""
    found: set[str] = set()
    for raw in (additives or "").split(","):
        tag = raw.strip().lower()
        if ":" in tag:
            tag = tag.rsplit(":", 1)[1]
        cat = _ADDITIVE_FLAGS.get(tag)
        if cat is not None:
            found.add(cat)
    return found


# ---- nutrient helpers ----------------------------------------------------------


def _fmt(n: float) -> str:
    return f"{round(n, 1):g}"


def _serving_grams(food) -> tuple[float, bool]:
    """The grams (or mL) one serving weighs, for scaling per-100 nutrition, and
    whether that came from a named serving. The first named serving when there
    is one, else 100 (per-100 read as-is) with has_serving False."""
    servings = getattr(food, "servings", None) or []
    if servings:
        grams = getattr(servings[0], "grams", None)
        if grams:
            return float(grams), True
    return 100.0, False


# ---- the assessment ------------------------------------------------------------


def assess(food, added_sugar_threshold: float) -> Assessment:
    """Read a food and return its verdict tier and flags. `food` supplies
    ingredients_text, additives, nova_group, the per-100 nutrition columns, and
    servings; anything missing reads as absent (a custom food, or a scan that
    couldn't be enriched)."""
    ingredients_text = getattr(food, "ingredients_text", None) or ""
    additives = getattr(food, "additives", None) or ""
    nova_group = getattr(food, "nova_group", None)
    has_data = bool(ingredients_text.strip()) or bool(additives.strip()) or (
        nova_group is not None
    )

    haystack = _normalize(ingredients_text)
    tag_categories = _additive_categories(additives)

    flags: list[Flag] = []
    seen: set[tuple[str, str]] = set()

    def add(category: str, severity: str, label: str, detail: str) -> None:
        key = (category, label)
        if key in seen:
            return
        seen.add(key)
        flags.append(Flag(category, severity, label, detail))

    # Ingredient-term and additive-tag rules (deduped by category+label).
    for rule, patterns in _RULE_PATTERNS:
        if _text_hit(patterns, haystack) or rule.category in tag_categories:
            add(rule.category, rule.severity, rule.label, rule.detail)

    # Nutrient thresholds, evaluated per serving (or per 100 when the food has
    # no named serving, in which case the detail says so).
    serving_g, has_serving = _serving_grams(food)
    scale = serving_g / 100.0
    if has_serving:
        per = "per serving"
    elif getattr(food, "base_unit", "g") == "ml":
        per = "per 100 mL"
    else:
        per = "per 100 g"
    trans = getattr(food, "trans_fat_g", None)
    if trans is not None and trans * scale > 0:
        add(
            "trans_fat",
            "bad",
            "Trans fat",
            "Contains trans fat, which has no safe level of intake.",
        )
    sat = getattr(food, "saturated_fat_g", None)
    if sat is not None and sat * scale >= 4:
        add(
            "sat_fat",
            "warn",
            "High in saturated fat",
            f"About {_fmt(sat * scale)} g of saturated fat {per}.",
        )
    sodium = getattr(food, "sodium_mg", None)
    if sodium is not None and sodium * scale >= 460:
        add(
            "sodium",
            "warn",
            "High in sodium",
            f"About {_fmt(sodium * scale)} mg of sodium {per}.",
        )

    # Added sugar: the reported nutrient when present, else the ingredient
    # aliases (a "bad" without a quantity), else a weak warning on total sugar.
    # The product IS the sweetener (a jar of honey, a bag of cane sugar) when its
    # sole ingredient is itself an added-sugar alias: nothing was added, so skip
    # the whole chain regardless of a reported nutrient (US labels still declare
    # honey's own sugars as "added").
    sole = _sole_ingredient(ingredients_text)
    is_the_sweetener = sole is not None and _text_hit(
        _ADDED_SUGAR_PATTERNS, _normalize(sole)
    )
    added = getattr(food, "added_sugar_g", None)
    if is_the_sweetener:
        pass
    elif added is not None:
        if added * scale >= added_sugar_threshold:
            add(
                "added_sugar",
                "bad",
                "Added sugar",
                f"About {_fmt(added * scale)} g of added sugar {per}, over "
                f"the {_fmt(added_sugar_threshold)} g limit.",
            )
    elif _text_hit(_ADDED_SUGAR_PATTERNS, haystack):
        add(
            "added_sugar",
            "bad",
            "Added sugar",
            "Lists added sugar in its ingredients (the label does not break out "
            "how much).",
        )
    else:
        total = getattr(food, "sugar_g", None)
        if total is not None and total * scale >= added_sugar_threshold:
            add(
                "sugar",
                "warn",
                "High in sugar",
                f"About {_fmt(total * scale)} g of total sugar {per}; the "
                "label does not separate added from natural sugar.",
            )

    # NOVA processing class: a warning at the top, a positive note at the bottom.
    if nova_group == 4:
        add(
            "nova",
            "warn",
            "Ultra-processed",
            "Classified as an ultra-processed food (NOVA group 4).",
        )
    elif nova_group == 1:
        add(
            "nova",
            "info",
            "Whole or minimally processed",
            "Classified as a whole or minimally processed food (NOVA group 1).",
        )

    if not has_data:
        add(
            "data",
            "info",
            "Limited data",
            "No ingredient list for this product; only the nutrition numbers "
            "were checked.",
        )

    flags.sort(key=lambda f: _SEVERITY_ORDER.get(f.severity, 9))

    substantive = [f for f in flags if f.severity != "info"]
    bad = [f for f in substantive if f.severity == "bad"]
    hydrogenated = any(f.category == "hydrogenated" for f in flags)

    if hydrogenated or len(bad) >= 2:
        verdict = "poor"
    elif bad:
        verdict = "mixed"
    elif substantive:  # warnings only
        verdict = "mixed"
    elif nova_group == 1:
        verdict = "whole"
    elif has_data:
        verdict = "clean"
    else:
        verdict = "unknown"

    return Assessment(verdict=verdict, flags=flags)
