def flatten_json(data):
    parts = []

    if isinstance(data, dict):
        for v in data.values():
            parts.append(flatten_json(v))

    elif isinstance(data, list):
        for v in data:
            parts.append(flatten_json(v))

    else:
        parts.append(str(data))

    return " ".join(parts)
