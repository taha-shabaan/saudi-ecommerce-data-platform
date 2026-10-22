"""
Extensible Generator Registry with Typed Configuration & Multi-Locale Support.
"""

from typing import Callable, Dict, Any, List, Optional
from dataclasses import dataclass, field
import uuid
import random
from datetime import datetime, date
from faker import Faker


@dataclass
class GeneratorContext:
    """Contextual metadata passed to each generator invocation."""
    locale: str = "en_US"
    row_index: int = 0
    params: Dict[str, Any] = field(default_factory=dict)
    noise_rate: float = 0.0
    current_record: Dict[str, Any] = field(default_factory=dict)
    pk_pools: Dict[str, List[Any]] = field(default_factory=dict)


@dataclass
class GeneratorMeta:
    """Metadata describing a registered synthetic generator."""
    name: str
    sql_type: str
    parquet_type: str
    localized: bool
    description: str
    handler: Callable[[GeneratorContext, Faker], Any]


class GeneratorRegistry:
    """Central registry for synthetic data generator strategies."""
    
    _generators: Dict[str, GeneratorMeta] = {}
    _faker_cache: Dict[str, Faker] = {}
    _fallback_faker: Optional[Faker] = None

    @classmethod
    def get_faker(cls, locale: str) -> Faker:
        """Retrieves or instantiates a cached Faker instance for the given locale."""
        if locale not in cls._faker_cache:
            try:
                cls._faker_cache[locale] = Faker(locale)
            except Exception:
                # If locale is invalid, fallback to en_US
                if cls._fallback_faker is None:
                    cls._fallback_faker = Faker("en_US")
                return cls._fallback_faker
        return cls._faker_cache[locale]

    @classmethod
    def register(
        cls,
        name: str,
        sql_type: str = "VARCHAR(255)",
        parquet_type: str = "BYTE_ARRAY",
        localized: bool = False,
        description: str = ""
    ):
        """Decorator to register a generator function."""
        def decorator(fn: Callable[[GeneratorContext, Faker], Any]):
            cls._generators[name] = GeneratorMeta(
                name=name,
                sql_type=sql_type,
                parquet_type=parquet_type,
                localized=localized,
                description=description,
                handler=fn
            )
            return fn
        return decorator

    @classmethod
    def list_generators(cls) -> List[str]:
        """Returns list of registered generator keys."""
        return sorted(list(cls._generators.keys()))

    @classmethod
    def get_meta(cls, name: str) -> Optional[GeneratorMeta]:
        """Returns metadata for a specific generator."""
        return cls._generators.get(name)

    @classmethod
    def generate(cls, generator_type: str, context: GeneratorContext) -> Any:
        """
        Executes a registered generator, applying multi-locale support
        and optional controlled data noise.
        """
        meta = cls._generators.get(generator_type)
        if not meta:
            raise ValueError(f"Unknown generator type '{generator_type}'. Available: {cls.list_generators()}")

        faker_instance = cls.get_faker(context.locale)

        # Generate base value with fallback to en_US if locale provider fails
        try:
            val = meta.handler(context, faker_instance)
        except Exception:
            if cls._fallback_faker is None:
                cls._fallback_faker = Faker("en_US")
            val = meta.handler(context, cls._fallback_faker)

        # Apply controlled data noise if applicable
        if context.noise_rate > 0.0 and generator_type not in ["autoincrement", "foreign_key"]:
            val = cls.apply_noise(val, generator_type, context.noise_rate)

        return val

    @classmethod
    def apply_noise(cls, val: Any, generator_type: str, noise_rate: float) -> Any:
        """Injects realistic formatting anomalies, untrimmed whitespace, or sentinels."""
        if random.random() >= noise_rate:
            return val

        anomaly_type = random.choice(["whitespace", "sentinel", "corruption"])

        if anomaly_type == "whitespace" and isinstance(val, str):
            return f"   {val}  "
        elif anomaly_type == "sentinel":
            return random.choice(["N/A", "NULL", "None", "-", ""])
        else:
            if generator_type == "email" and isinstance(val, str):
                return val.replace("@", "_at_")
            elif generator_type == "phone" and isinstance(val, str):
                return "000-INVALID-PHONE"
            elif generator_type == "uuid":
                return "00000000-0000-0000-0000-000000000000"
            return f"{val}_CORRUPTED"


# =====================================================================
# CORE GENERATOR IMPLEMENTATIONS
# =====================================================================

@GeneratorRegistry.register("autoincrement", sql_type="SERIAL PRIMARY KEY", parquet_type="INT64", description="Sequential integer sequence")
def _gen_autoincrement(ctx: GeneratorContext, faker: Faker) -> int:
    start = ctx.params.get("start", 1)
    step = ctx.params.get("step", 1)
    return start + (ctx.row_index * step)


@GeneratorRegistry.register("uuid", sql_type="UUID", parquet_type="BYTE_ARRAY", description="UUID Version 4 identifier")
def _gen_uuid(ctx: GeneratorContext, faker: Faker) -> str:
    return str(uuid.uuid4())


@GeneratorRegistry.register("full_name", sql_type="VARCHAR(255)", parquet_type="BYTE_ARRAY", localized=True, description="Localized full name")
def _gen_full_name(ctx: GeneratorContext, faker: Faker) -> str:
    return faker.name()


@GeneratorRegistry.register("first_name", sql_type="VARCHAR(100)", parquet_type="BYTE_ARRAY", localized=True, description="Localized first name")
def _gen_first_name(ctx: GeneratorContext, faker: Faker) -> str:
    return faker.first_name()


@GeneratorRegistry.register("last_name", sql_type="VARCHAR(100)", parquet_type="BYTE_ARRAY", localized=True, description="Localized last name")
def _gen_last_name(ctx: GeneratorContext, faker: Faker) -> str:
    return faker.last_name()


@GeneratorRegistry.register("email", sql_type="VARCHAR(255)", parquet_type="BYTE_ARRAY", localized=True, description="Realistic email address")
def _gen_email(ctx: GeneratorContext, faker: Faker) -> str:
    return faker.email()


@GeneratorRegistry.register("phone", sql_type="VARCHAR(50)", parquet_type="BYTE_ARRAY", localized=True, description="Localized telephone number")
def _gen_phone(ctx: GeneratorContext, faker: Faker) -> str:
    return faker.phone_number()


@GeneratorRegistry.register("street_address", sql_type="VARCHAR(255)", parquet_type="BYTE_ARRAY", localized=True, description="Localized street address")
def _gen_street_address(ctx: GeneratorContext, faker: Faker) -> str:
    return faker.street_address()


@GeneratorRegistry.register("city", sql_type="VARCHAR(100)", parquet_type="BYTE_ARRAY", localized=True, description="Localized city name")
def _gen_city(ctx: GeneratorContext, faker: Faker) -> str:
    return faker.city()


@GeneratorRegistry.register("country", sql_type="VARCHAR(100)", parquet_type="BYTE_ARRAY", localized=True, description="Localized country name")
def _gen_country(ctx: GeneratorContext, faker: Faker) -> str:
    return faker.country()


@GeneratorRegistry.register("date_time", sql_type="TIMESTAMP", parquet_type="INT64", description="Date or timestamp within configured range")
def _gen_date_time(ctx: GeneratorContext, faker: Faker) -> str:
    start_str = ctx.params.get("start_date", "-2y")
    end_str = ctx.params.get("end_date", "now")
    date_val = faker.date_time_between(start_date=start_str, end_date=end_str)
    fmt = ctx.params.get("format", "%Y-%m-%d %H:%M:%S")
    return date_val.strftime(fmt)


@GeneratorRegistry.register("numeric_range", sql_type="INTEGER", parquet_type="INT64", description="Random number within range")
def _gen_numeric_range(ctx: GeneratorContext, faker: Faker) -> Any:
    min_val = ctx.params.get("min", 1)
    max_val = ctx.params.get("max", 1000)
    is_float = ctx.params.get("is_float", False)
    if is_float:
        precision = ctx.params.get("precision", 2)
        return round(random.uniform(float(min_val), float(max_val)), precision)
    return random.randint(int(min_val), int(max_val))


@GeneratorRegistry.register("categorical", sql_type="VARCHAR(100)", parquet_type="BYTE_ARRAY", description="Discrete categorical choice")
def _gen_categorical(ctx: GeneratorContext, faker: Faker) -> str:
    choices = ctx.params.get("choices", ["Option A", "Option B", "Option C"])
    weights = ctx.params.get("weights", None)
    if weights and len(weights) == len(choices):
        return random.choices(choices, weights=weights, k=1)[0]
    return random.choice(choices)


@GeneratorRegistry.register("boolean", sql_type="BOOLEAN", parquet_type="BOOLEAN", description="True/false boolean flag")
def _gen_boolean(ctx: GeneratorContext, faker: Faker) -> bool:
    true_prob = ctx.params.get("true_probability", 0.5)
    return random.random() < true_prob


@GeneratorRegistry.register("text", sql_type="TEXT", parquet_type="BYTE_ARRAY", localized=True, description="Paragraph or sentence text")
def _gen_text(ctx: GeneratorContext, faker: Faker) -> str:
    nb_sentences = ctx.params.get("sentences", 3)
    return faker.paragraph(nb_sentences=nb_sentences)
