def clean_text(text):
    if text is None:
        return None

    text = ftfy.fix_text(text)

    replacements = {
        "â€™": "'",
        "â€˜": "'",
        "â€œ": '"',
        "â€": '"',
        "â€“": "-",
        "â€”": "-",
        "Â»": "»",
        "Â·": "·",
        "\u00a0": " ",
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-"
    }

    for bad, good in replacements.items():
        text = text.replace(bad, good)

    text = re.sub(r"[\u200b-\u200d\ufeff]", "", text)

    return text


