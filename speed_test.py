#!/usr/bin/env python3
"""Замер скорости загрузки: N последовательных GET-запросов к URL."""

from __future__ import annotations

import argparse
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
DEFAULT_REQUESTS = 10
USER_AGENT = "internet-speed-test/1.0"
MiB = 1024 * 1024
ALLOWED_SCHEMES = frozenset({"http", "https"})


def build_ssl_context() -> ssl.SSLContext:
    """Контекст TLS с корневыми сертификатами certifi (HTTPS на macOS/Windows)."""
    ctx = ssl.create_default_context()
    try:
        import certifi

        ctx.load_verify_locations(certifi.where())
    except ImportError:
        pass
    return ctx


SSL_CONTEXT = build_ssl_context()


def format_bytes(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def describe_request_error(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}: {exc.reason or 'ошибка сервера'}"

    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, ssl.SSLError):
            hint = (
                " Проверьте URL и установите зависимости: pip install -r requirements.txt"
            )
            return f"ошибка SSL/TLS: {reason.reason or reason}{hint}"
        if isinstance(reason, socket.timeout):
            return "превышено время ожидания ответа (timeout)"
        if isinstance(reason, TimeoutError):
            return "превышено время ожидания ответа"
        if isinstance(reason, ConnectionRefusedError):
            return "соединение отклонено (connection refused)"
        if isinstance(reason, OSError):
            return f"сетевая ошибка: {reason}"
        return f"ошибка URL: {reason}"

    if isinstance(exc, socket.timeout):
        return "превышено время ожидания ответа (timeout)"

    if isinstance(exc, TimeoutError):
        return "превышено время ожидания ответа"

    return str(exc)


def validate_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        print("Ошибка: укажите полный URL, например https://example.com/file.jpg", file=sys.stderr)
        sys.exit(2)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        print(
            f"Ошибка: поддерживаются только http и https, получено: {parsed.scheme!r}",
            file=sys.stderr,
        )
        sys.exit(2)
    return url.strip()


def fetch(url: str, timeout: float) -> tuple[float, int]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout,
            context=SSL_CONTEXT,
        ) as response:
            body = response.read()
    except urllib.error.HTTPError:
        raise
    except urllib.error.URLError:
        raise
    except (TimeoutError, socket.timeout) as exc:
        raise urllib.error.URLError(exc) from exc

    elapsed = time.perf_counter() - start
    return elapsed, len(body)


def run(url: str, count: int, timeout: float) -> int:
    times: list[float] = []
    total_bytes = 0
    failed = 0

    print(f"Адрес: {url}")
    print(f"Запросов: {count} (последовательно)\n")
    sys.stdout.flush()

    for i in range(1, count + 1):
        try:
            elapsed, nbytes = fetch(url, timeout)
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
            failed += 1
            print(f"  #{i}: ошибка — {describe_request_error(exc)}")
            continue

        if nbytes == 0:
            print(f"  #{i}: предупреждение — пустое тело ответа (0 байт)")

        times.append(elapsed)
        total_bytes += nbytes
        print(f"  #{i}: {elapsed:.3f} с, {format_bytes(nbytes)} байт")

    print()
    if not times:
        print("Итог: ни одного успешного запроса. Скорость не рассчитана.", file=sys.stderr)
        return 1

    if failed:
        print(f"Успешно: {len(times)} из {count}, ошибок: {failed}")

    avg_time = sum(times) / len(times)
    total_time = sum(times)
    speed_mib_s = (total_bytes / total_time) / MiB if total_time > 0 else 0.0

    print(f"Среднее время запроса: {avg_time:.3f} с")
    print(
        f"Объём данных:          {format_bytes(total_bytes)} байт "
        f"({total_bytes / MiB:.2f} МиБ)"
    )
    print(f"Скорость:              {speed_mib_s:.2f} МБ/с")
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Замер скорости загрузки по последовательным HTTP/HTTPS GET-запросам.",
    )
    parser.add_argument(
        "url",
        help="URL файла для загрузки (например, большая картинка по https)",
    )
    parser.add_argument(
        "-n",
        "--count",
        type=int,
        default=DEFAULT_REQUESTS,
        metavar="N",
        help=f"число запросов (по умолчанию: {DEFAULT_REQUESTS})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        metavar="СЕК",
        help="таймаут одного запроса в секундах (по умолчанию: 120)",
    )
    args = parser.parse_args()

    if args.count < 1:
        print("Ошибка: число запросов должно быть не меньше 1", file=sys.stderr)
        return 2

    if args.timeout <= 0:
        print("Ошибка: таймаут должен быть больше 0", file=sys.stderr)
        return 2

    url = validate_url(args.url)

    try:
        return run(url, args.count, args.timeout)
    except KeyboardInterrupt:
        print("\nПрервано пользователем.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
