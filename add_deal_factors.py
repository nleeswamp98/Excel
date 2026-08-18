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
