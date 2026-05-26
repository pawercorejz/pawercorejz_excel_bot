def process_zvonok(file_path):
    wb = load_workbook(file_path, read_only=True, data_only=True)
    ws = wb.active

    rows = ws.iter_rows(values_only=True)
    headers = next(rows)

    headers_lower = [str(h).strip().lower() if h else "" for h in headers]

    phone_col = None
    status_col = None
    client_answer_col = None

    for i, h in enumerate(headers_lower):
        if "номер" in h and "телефон" in h:
            phone_col = i

        if "статус звонка" in h:
            status_col = i

        if "транскрибация клиента" in h or "ответ клиента" in h:
            client_answer_col = i

    if phone_col is None or status_col is None:
        raise Exception("Не нашёл столбцы 'Номер телефона' и 'Статус звонка'.")

    if client_answer_col is None:
        raise Exception("Не нашёл столбец с ответом клиента.")

    bad_answers = [
        "номер набран неправильно",
        "проверьте корректность наборам",
        "номер не используется",
    ]

    numbers = []

    for row in rows:
        status = str(row[status_col]).strip().lower() if row[status_col] else ""
        client_answer = str(row[client_answer_col]).strip().lower() if row[client_answer_col] else ""

        if status == "закончен удачно":
            # пропускаем плохие ответы
            if any(bad in client_answer for bad in bad_answers):
                continue

            phone = clean_phone(row[phone_col])
            if phone:
                numbers.append(phone)

    return numbers
    
