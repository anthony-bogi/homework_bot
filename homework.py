import logging
import os
import time
from http import HTTPStatus

import requests
import telegram
from dotenv import load_dotenv

from constants import *
from exceptions import APIAnswerError

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

formatter = logging.Formatter(
    '%(asctime)s, %(levelname)s, %(message)s'
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(stream='sys.stdout')
handler.setFormatter(formatter)
logger.addHandler(handler)

error_cache = []


def check_tokens():
    """Проверка доступности переменных окружения."""
    return PRACTICUM_TOKEN and TELEGRAM_TOKEN and TELEGRAM_CHAT_ID


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(f'Сообщение {message} отправлено пользователю.')
    except Exception as error:
        logger.error(f'Сообщение не отправлено. Ошибка {error}.')


def error_log_and_inf_in_telegram(bot, message):
    """
    Логирование событий уровня ERROR.
    Если возможно, однократно отправляется информация
    об ошибках в Телеграм.
    """
    logger.error(message)
    if message not in error_cache:
        try:
            send_message(bot, message)
            error_cache.append(message)
        except Exception as error:
            logger.info('Сообщение об ошибке отправить не удалось: '
                        f'{error}')


def get_api_answer(timestamp):
    """
    Запрос к единственному эндпоинту API-сервиса.
    Возвращает ответ API в формате типа данныз Python.
    """
    payload = {'from_date': timestamp}

    try:
        homework_statuses = requests.get(ENDPOINT,
                                         headers=HEADERS,
                                         params=payload
                                         )
        if homework_statuses.status_code != HTTPStatus.OK:
            raise Exception('Эндпоинт недоступен.')
    except Exception:
        raise APIAnswerError('Незапланированная работа API.')

    homework_statuses = homework_statuses.json()
    return homework_statuses


def check_response(response):
    """Проверка ответа API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError('Ошибка в типе данных: ответ должен содержать '
                        'словарь.')

    keys = response.keys()

    if 'homeworks' not in keys:
        raise KeyError('Отсутсвует ключ homeworks.')

    if not isinstance(response['homeworks'], list):
        raise TypeError('Ошибка в типе данных: ответ должен содержать список.')

    if ['homeworks'][0] not in response:
        raise IndexError('Домашняя работа отсутсвует в списке.')

    homework = response['homeworks'][0]

    return homework


def parse_status(homework):
    """Извлекает статус конкретной работы."""
    keys = ['homework_name', 'status']

    for key in keys:
        if key not in homework:
            raise KeyError(f'Ключа {key} нет в ответе API.')

    homework_status = homework['status']

    if homework_status not in HOMEWORK_VERDICTS:
        raise KeyError('Неожиданный статус домашней работы.')

    homework_name = homework['homework_name']
    verdict = HOMEWORK_VERDICTS[homework_status]

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""

    if not check_tokens():
        logger.critical('Отсутствуют обязательные переменные окружения!')
        raise SystemExit()

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time()) - THREE_WEEKS_SEC

    cache = []

    while True:
        try:
            response = get_api_answer(timestamp)
            homework = check_response(response)
            message = parse_status(homework)
            if message in cache:
                logger.debug('Новый статус ДЗ отсутсвует.')
            else:
                cache.append(message)
                send_message(bot, message)
        except Exception as error:
            message = (f'Сбой в работе программы: {error}')
            error_log_and_inf_in_telegram(bot, message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
