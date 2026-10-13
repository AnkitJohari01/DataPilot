"""Preserve explicit dataset units; use the user's USD default only when absent."""
import re

_CODES = "AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB BRL BSD BTN BWP BYN BZD CAD CDF CHF CLP CNY COP CRC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD HNL HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SLL SOS SRD SSP STN SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD UYU UZS VES VND VUV WST XAF XCD XCG XOF XPF YER ZAR ZMW ZWG".split()
_MARKERS = re.compile(r"US\$|CA\$|AU\$|NZ\$|HK\$|S\$|R\$|[₹$€£¥₩₽₺₫₱฿৳₦₪]|(?<![A-Za-z])(?:" + "|".join(_CODES) + r")(?![A-Za-z])")
_ALIASES = {"USD": "$", "US$": "$", "INR": "₹", "EUR": "€", "GBP": "£", "CAD": "CA$", "AUD": "AU$", "NZD": "NZ$", "HKD": "HK$", "SGD": "S$", "BRL": "R$"}


def currency_markers(value: str) -> set[str]:
    # Excel's [$-409] is a locale marker, not a dollar currency format.
    value = re.sub(r"\[\$-[0-9a-fA-F]+\]", "", value)
    return {_ALIASES.get(match, match) for match in _MARKERS.findall(value)}


def dataframe_currency_context(frame) -> dict[str, list[str]]:
    context = dict(frame.attrs.get("currency_context", {}))
    for column in frame.columns:
        label = str(column)
        markers = currency_markers(label) | set(context.get(label, []))
        if re.search(r"currency|sales|revenue|profit|price|cost|amount|spend|value", label, re.I):
            for value in frame[column].dropna().unique():
                if isinstance(value, str):
                    markers |= currency_markers(value)
                    if re.search(r"currency", label, re.I) and re.fullmatch(r"[A-Z]{3}", value.strip()):
                        markers.add(_ALIASES.get(value.strip(), value.strip()))
        if markers:
            context[label] = sorted(markers)
    return context


def build_currency_context(schema_text: str, rows: list[dict]) -> str:
    lines = [line for line in schema_text.splitlines() if currency_markers(line) or re.search(r"currency", line, re.I)]
    for row in rows:
        for column, value in row.items():
            if currency_markers(str(column)) or currency_markers(str(value)) or re.search(r"currency", column, re.I):
                lines.append(f"{column}: {value}")
    return "\n".join(dict.fromkeys(lines))


def output_currency(context: str) -> str | None:
    markers = currency_markers(context)
    for line in context.splitlines():
        if re.search(r"currency", line, re.I):
            markers |= {_ALIASES.get(code, code) for code in re.findall(r"\b[A-Z]{3}\b", line)}
    if not markers:
        return "$"
    return next(iter(markers)) if len(markers) == 1 else None
