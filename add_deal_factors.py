def parse_deal_factor_section(section_text):
    factors = []

    if not section_text:
        return factors

    factor_start_pattern = re.compile(
        r"^\s*(?:(?:»|>>>|•)\s*)?"
        r"(?![-–—◦▪])"
        r"([^:\n]{2,120})"
        r"\s*:\s*(.*)$"
    )

    sub_bullet_pattern = re.compile(
        r"^\s*(?:[-–—◦▪]+)\s*"
    )

    current_label = None
    current_text_parts = []

    for raw_line in section_text.splitlines():
        line = raw_line.strip()

        if not line:
            continue

        line = line.replace("Â»", "»")
        line = line.replace("â€™", "'")

        match = factor_start_pattern.match(line)

        if match:
            if current_label is not None:
                factor_text = " ".join(current_text_parts).strip()

                if factor_text:
                    factors.append(
                        (current_label, factor_text)
                    )

            current_label = match.group(1).strip()
            current_text_parts = []

            first_description = match.group(2).strip()

            if first_description:
                current_text_parts.append(first_description)

            continue

        if current_label is not None:
            continuation = sub_bullet_pattern.sub("", line).strip()

            if continuation:
                current_text_parts.append(continuation)

    if current_label is not None:
        factor_text = " ".join(current_text_parts).strip()

        if factor_text:
            factors.append(
                (current_label, factor_text)
            )

    return factors


def extract_deal_factors_text(full_text):
    try:
        strengths_idx = config_v2.PRESALE_CONTENTS.index(
            "Credit strengths"
        )

        challenges_idx = config_v2.PRESALE_CONTENTS.index(
            "Credit challenges"
        )

    except ValueError:
        return None, None

    def extract_section(start_heading, end_heading):
        start_pattern = re.compile(
            r"^\s*"
            + re.escape(start_heading)
            + r"\s*$",
            re.IGNORECASE | re.MULTILINE
        )

        end_pattern = re.compile(
            r"^\s*"
            + re.escape(end_heading)
            + r"\s*$",
            re.IGNORECASE | re.MULTILINE
        )

        start_matches = list(
            start_pattern.finditer(full_text)
        )

        if not start_matches:
            return None

        start_match = start_matches[-1]
        text_after = full_text[start_match.end():]

        end_match = end_pattern.search(text_after)

        if end_match:
            return text_after[:end_match.start()].strip()

        return text_after.strip()

    strengths_end = config_v2.PRESALE_CONTENTS[
        strengths_idx + 1
    ]

    challenges_end = config_v2.PRESALE_CONTENTS[
        challenges_idx + 1
    ]

    strengths_text = extract_section(
        "Credit strengths",
        strengths_end
    )

    challenges_text = extract_section(
        "Credit challenges",
        challenges_end
    )

    return strengths_text, challenges_text
