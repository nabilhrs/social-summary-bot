from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.bot.timeparse import parse_reminder

KL = ZoneInfo("Asia/Kuala_Lumpur")
NOW = datetime(2026, 11, 18, 15, 0, tzinfo=KL)  # Wednesday 3:00pm


def at(month, day, hour, minute=0, year=2026):
    return datetime(year, month, day, hour, minute, tzinfo=KL)


@pytest.mark.parametrize(
    "text, when, rest",
    [
        # English
        ("tomorrow 7am dentist appointment", at(11, 19, 7), "dentist appointment"),
        ("tmr 8:30am standup", at(11, 19, 8, 30), "standup"),
        ("in 2 hours call mum", at(11, 18, 17), "call mum"),
        ("in 30 minutes take the cake out", at(11, 18, 15, 30), "take the cake out"),
        ("in 30min stretch", at(11, 18, 15, 30), "stretch"),
        ("in an hour check the oven", at(11, 18, 16), "check the oven"),
        ("in 3 days pay rent", at(11, 21, 15), "pay rent"),
        ("fri 3pm submit the report", at(11, 20, 15), "submit the report"),
        ("friday submit the report", at(11, 20, 9), "submit the report"),
        ("next monday 10am interview", at(11, 23, 10), "interview"),
        ("25/11 9:30am renew road tax", at(11, 25, 9, 30), "renew road tax"),
        ("25 nov renew road tax", at(11, 25, 9), "renew road tax"),
        ("dec 3 7pm dinner", at(12, 3, 19), "dinner"),
        ("5/1 dentist", at(1, 5, 9, year=2027), "dentist"),  # already past this year: next year
        ("tonight take out the trash", at(11, 18, 20), "take out the trash"),
        ("tonight 9 call sis", at(11, 18, 21), "call sis"),
        ("tomorrow morning gym", at(11, 19, 9), "gym"),
        ("tomorrow evening call grandpa", at(11, 19, 18), "call grandpa"),
        ("at 8 water the plants", at(11, 18, 20), "water the plants"),  # next 8 o'clock: tonight
        ("7pm call the bank", at(11, 18, 19), "call the bank"),
        ("19:00 dinner with Aina", at(11, 18, 19), "dinner with Aina"),
        ("10am meeting", at(11, 19, 10), "meeting"),  # 10am already passed today
        ("tomorrow 7am to call the clinic", at(11, 19, 7), "call the clinic"),
        ("day after tomorrow 8am flight", at(11, 20, 8), "flight"),
        ("next week book the car service", at(11, 25, 9), "book the car service"),
        # Time at the end instead of the start
        ("dentist appointment tomorrow 7am", at(11, 19, 7), "dentist appointment"),
        ("call mum in 2 hours", at(11, 18, 17), "call mum"),
        ("submit report on friday at 3pm", at(11, 20, 15), "submit report"),
        # Malay
        ("esok pukul 8 pagi temujanji doktor", at(11, 19, 8), "temujanji doktor"),
        ("esok pagi pergi gym", at(11, 19, 9), "pergi gym"),
        ("esok jam 3 petang mesyuarat", at(11, 19, 15), "mesyuarat"),
        ("malam ini telefon mak", at(11, 18, 20), "telefon mak"),
        ("hari ini pukul 9 malam bayar bil", at(11, 18, 21), "bayar bil"),
        ("lusa 10 pagi hantar kereta", at(11, 20, 10), "hantar kereta"),
        ("2 jam lagi angkat kain", at(11, 18, 17), "angkat kain"),
        ("dalam 30 minit matikan dapur", at(11, 18, 15, 30), "matikan dapur"),
        ("lagi 15 minit keluar", at(11, 18, 15, 15), "keluar"),
        ("setengah jam lagi solat", at(11, 18, 15, 30), "solat"),
        ("sejam lagi ambil adik", at(11, 18, 16), "ambil adik"),
        ("3 hari lagi bayar sewa", at(11, 21, 15), "bayar sewa"),
        ("jumaat 2 petang hantar laporan", at(11, 20, 14), "hantar laporan"),
        ("isnin depan 9 pagi temuduga", at(11, 23, 9), "temuduga"),
        ("25 disember pukul 10 pagi hari jadi ayah", at(12, 25, 10), "hari jadi ayah"),
        ("besok tengah hari makan dengan Ali", at(11, 19, 12), "makan dengan Ali"),
        ("minggu depan servis kereta", at(11, 25, 9), "servis kereta"),
        ("temujanji doktor esok pukul 8 pagi", at(11, 19, 8), "temujanji doktor"),
    ],
)
def test_parse_reminder(text, when, rest):
    parsed = parse_reminder(text, NOW)
    assert parsed is not None, text
    assert (parsed.when, parsed.text) == (when, rest)


@pytest.mark.parametrize("text", ["buy milk", "call mum about the trip", "", "remember the 2 tickets"])
def test_no_time_means_none(text):
    assert parse_reminder(text, NOW) is None


def test_a_time_that_already_passed_today_is_returned_for_the_caller_to_reject():
    parsed = parse_reminder("today 7am gym", NOW)
    assert parsed.when == at(11, 18, 7) and parsed.when < NOW


def test_bare_numbers_inside_the_reminder_text_are_left_alone():
    parsed = parse_reminder("tomorrow 9am buy 2 tickets", NOW)
    assert (parsed.when, parsed.text) == (at(11, 19, 9), "buy 2 tickets")


def test_fillers_after_the_time_stay_in_the_text():
    parsed = parse_reminder("tomorrow 7am at the clinic", NOW)
    assert (parsed.when, parsed.text) == (at(11, 19, 7), "at the clinic")
