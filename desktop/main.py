import datetime
import json
import random
import sys
import threading
import time
from PyQt6 import uic
from PyQt6.QtWidgets import QWidget, QApplication, QMessageBox
import sqlite3
import requests


class Utils:
    class Logging:
        @staticmethod
        def log_to_txt(_error, _prefix: str, _print: bool = True):
            _message = f"{datetime.datetime.now()} {_prefix}: {_error}\n"
            if _print:
                print(_message)
            with open("error.txt", "a", encoding="utf-8") as f:
                f.write(_message)

    class Query:
        @staticmethod
        def create_table_params() -> str:
            return f"""
CREATE TABLE IF NOT EXISTS params (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL,
    value TEXT NOT NULL DEFAULT ''
);"""

        @staticmethod
        def create_table_history() -> str:
            return f"""
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL,
    value TEXT NOT NULL DEFAULT ''
);"""

        @staticmethod
        def get_all_params() -> str:
            return f"""
SELECT key, value 
FROM params
;"""

        @staticmethod
        def get_insert_or_replace_params() -> str:
            return f"""
INSERT OR REPLACE 
INTO params
    (key, value)
VALUES
    (:key, :value)
;"""

    @staticmethod
    def sql_execute(_query: str, _kwargs: dict, _source: str):
        try:
            with sqlite3.connect(f"src/database/{_source}") as _connection:
                _cursor = _connection.cursor()
                _cursor.execute(_query, _kwargs)
                _connection.commit()
                _data = _cursor.fetchall()
                return _data
        except Exception as error:
            Utils.Logging.log_to_txt(error, "sql_execute")

    class Service:
        @staticmethod
        def database_init():
            Utils.sql_execute(
                _query=Utils.Query.create_table_params(),
                _kwargs={},
                _source="local_settings.db",
            )
            Utils.sql_execute(
                _query=Utils.Query.create_table_history(),
                _kwargs={},
                _source="local_settings.db",
            )

        @staticmethod
        def get_all_params() -> dict:
            try:
                _rows = Utils.sql_execute(
                    _query=Utils.Query.get_all_params(),
                    _kwargs={},
                    _source="local_settings.db",
                )
                _dict = [{"key": str(x[0]), "value": str(x[1])} for x in _rows]
                _params = {}
                for i in _dict:
                    _params[i["key"]] = i["value"]
                return _params
            except Exception as error:
                Utils.Logging.log_to_txt(error, "get_all_params")
                return {}

        @staticmethod
        def load_conf_json() -> dict:
            with open("src/database/conf.json", "r", encoding="utf-8") as f:
                return json.load(f)


class Ui(QWidget):
    def __init__(self):
        super().__init__()
        self.ui = uic.loadUi("src/ui/main.ui", self)
        self.__alive = True
        self.__params = {}

        self.ui.pushButton_temp_plan_plus.clicked.connect(self.push_button_temp_plan_plus)
        self.ui.pushButton_temp_plan_minus.clicked.connect(self.push_button_temp_plan_minus)

        self.show()
        threading.Thread(target=self.loops, args=()).start()

    def closeEvent(self, event):
        # Создаем диалоговое окно для подтверждения закрытия
        reply = QMessageBox.question(
            self,
            "Подтверждение закрытия",
            "Вы уверены, что хотите закрыть окно?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.__alive = False
            event.accept()
        else:
            event.ignore()

    def push_button_temp_plan_plus(self):
        try:
            _params = Utils.Service.get_all_params()

            _temp_plan_high = int(_params.get("temp_plan_high", -7)) + 1
            _temp_plan_down = int(_params.get("temp_plan_down", -20)) + 1
            _data = {"temp_plan_high": _temp_plan_high, "temp_plan_down": _temp_plan_down}
            _text = ""
            for k, v in _data.items():
                _text += f"('{k}', '{v}'), "
            Utils.sql_execute(
                _query=f"""
            INSERT OR REPLACE 
            INTO params
                (key, value)
            VALUES
                {_text[:-2]} 
            ;""",
                _kwargs={},
                _source="local_settings.db",
            )
            threading.Thread(target=self.sync_settings_to_web, args=()).start()
        except Exception as error:
            Utils.Logging.log_to_txt(error, "push_button_temp_plan_plus")

    def push_button_temp_plan_minus(self):
        try:
            _params = Utils.Service.get_all_params()

            _temp_plan_high = int(_params.get("temp_plan_high", -7)) - 1
            _temp_plan_down = int(_params.get("temp_plan_down", -20)) - 1
            _data = {"temp_plan_high": _temp_plan_high, "temp_plan_down": _temp_plan_down}
            _text = ""
            for k, v in _data.items():
                _text += f"('{k}', '{v}'), "
            Utils.sql_execute(
                _query=f"""
                        INSERT OR REPLACE 
                        INTO params
                            (key, value)
                        VALUES
                            {_text[:-2]} 
                        ;""",
                _kwargs={},
                _source="local_settings.db",
            )
            print("push_button_temp_plan_minus")
            threading.Thread(target=self.sync_settings_to_web, args=()).start()
        except Exception as error:
            Utils.Logging.log_to_txt(error, "push_button_temp_plan_minus")

    def sync_settings_to_web(self):
        try:
            print("sync_settings_to_web")

            # Sheduler(планировщик)
            now = datetime.datetime.now()
            if now.hour < 8 or now.hour > 23:  # !23 > now.hour < 8
                print("skip")
                return

            _params = Utils.Service.get_all_params()

            print("requests.post")
            _response = requests.post(
                url=f"{conf['PROTOCOL']}://{conf['HOST']}:{conf['PORT']}/api/params/",
                headers={"Authorization": "Token=auth1234"},
                json={"serial_id": conf["SERIAL_ID"], "params": _params},
            )
            print(_response.status_code)
            if _response.status_code not in (200, 201):
                raise Exception(f"web {_response.status_code}")
        except Exception as error:
            Utils.Logging.log_to_txt(error, "sync_settings_to_web")

    def loops(self):
        def loop_update_ui_from_local_settings():
            while self.__alive:
                try:
                    _params = Utils.Service.get_all_params()

                    self.__params["temp_fact_high"] = int(_params.get("temp_fact_high", -7))
                    self.__params["temp_plan_high"] = int(_params.get("temp_plan_high", -7))

                    self.__params["temp_fact_down"] = int(_params.get("temp_fact_down", -7))
                    self.__params["temp_plan_down"] = int(_params.get("temp_plan_down", -20))

                    self.ui.label_temp_fact_high.setText(str(self.__params["temp_fact_high"]))
                    self.ui.label_temp_plan_high.setText(str(self.__params["temp_plan_high"]))

                    self.ui.label_temp_fact_down.setText(str(self.__params["temp_fact_down"]))
                    self.ui.label_temp_plan_down.setText(str(self.__params["temp_plan_down"]))
                except Exception as error:
                    Utils.Logging.log_to_txt(error, "update_ui_from_local_settings")
                time.sleep(conf["delay_loop_update_ui_from_local_settings"])

        def loop_sync_settings_from_web():
            while self.__alive:
                try:
                    _response = requests.get(
                        f"{conf['PROTOCOL']}://{conf['HOST']}:{conf['PORT']}/api/params/?serial_id={conf['SERIAL_ID']}",
                        headers={"Authorization": "Token=auth123"},
                    )
                    if _response.status_code not in (200, 201):
                        raise Exception(f"web {_response.status_code}")
                    _params = _response.json().get("data", {}).get("params", {})
                    _text = ""
                    for k, v in _params.items():
                        _text += f"('{k}', '{v}'), "
                    Utils.sql_execute(
                        _query=f"""
                        INSERT OR REPLACE 
                        INTO params
                            (key, value)
                        VALUES
                            {_text[:-2]} 
                        ;""",
                        _kwargs={},
                        _source="local_settings.db",
                    )
                except Exception as error:
                    Utils.Logging.log_to_txt(error, "sync_settings_from_web")
                time.sleep(5.0)

        def loop_emulate_temp_change():
            while self.__alive:
                try:
                    #
                    _temp_fact_high = random.randint(-17, -7)
                    _temp_fact_down = random.randint(-25, -17)
                    _data = {"temp_fact_high": _temp_fact_high, "temp_fact_down": _temp_fact_down}

                    #
                    _text = ""
                    for k, v in _data.items():
                        _text += f"('{k}', '{v}'), "

                    #
                    Utils.sql_execute(
                        _query=f"""
                            INSERT OR REPLACE 
                            INTO params
                                (key, value)
                            VALUES
                                {_text[:-2]} 
                            ;""",
                        _kwargs={},
                        _source="local_settings.db",
                    )
                except Exception as error:
                    Utils.Logging.log_to_txt(error, "loop_emulate_temp_change")
                time.sleep(1.0)

        def loop_simple_send_message():
            # Simple Исторические данные
            """
            Simple:
            1. Пакуем данные каждую секунду и отправляем на backend.
            - большая нагрузка на backend, потеря данных при ошибках, отсутвие регуляции нагрузки
            """
            while self.__alive:
                try:
                    #
                    _params = Utils.Service.get_all_params()

                    #
                    _response = requests.post(
                        url=f"{conf['PROTOCOL']}://{conf['HOST']}:{conf['PORT']}/api/messages/",
                        headers={"Authorization": "Token=auth12345"},
                        json={"serial_id": conf["SERIAL_ID"], "date_time_subsystem": str(datetime.datetime.now()), "params": _params},
                    )
                    if _response.status_code not in (200, 201):
                        raise Exception(f"web {_response.status_code}")
                except Exception as error:
                    Utils.Logging.log_to_txt(error, "loop_simple_send_message")
                time.sleep(1.0)

        threading.Thread(target=loop_update_ui_from_local_settings).start()
        threading.Thread(target=loop_sync_settings_from_web).start()
        threading.Thread(target=loop_simple_send_message).start()

        threading.Thread(target=loop_emulate_temp_change).start()


if __name__ == "__main__":
    conf = Utils.Service.load_conf_json()
    Utils.Service.database_init()
    app = QApplication(sys.argv)
    ui = Ui()
    sys.exit(app.exec())
