"""Private owner-only desktop tool. Never bundle this entry point with the client."""
from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import sqlite3
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import uuid

from merchant_service.owner_license import (
    PAYMENT_METHODS, PRIVATE_KEY_NAME, PUBLIC_KEY_NAME, REFERENCE,
    initialize_keys, issue_license, save_license,
)
from merchant_service.offline_license import INSTALLATION_ID, activation_code

METHODS = {"Бессрочно — только владелец": "owner",
           "Бесплатно — друг": "friend",
           "Банковский перевод (ручная проверка)": "bank_transfer",
           "Предметы Steam (ручная проверка)": "steam_items"}


def owner_directory() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "FPT-Owner-Licensing"


def validate_request(installation: str, days_text: str, method_label: str,
                     reconciled: bool) -> tuple[str, int | None, str]:
    installation = installation.strip()
    if not INSTALLATION_ID.fullmatch(installation):
        raise ValueError("Вставьте полный код установки из раздела «Подписка» лаунчера.")
    method = METHODS.get(method_label)
    if method is None:
        raise ValueError("Выберите способ выдачи доступа.")
    if days_text.strip().lower() in ("бессрочно", "навсегда"):
        days = None
    else:
        try:
            days = int(days_text)
        except ValueError:
            raise ValueError("Выберите срок или «Бессрочно».") from None
    if method == "owner" and days is not None:
        raise ValueError("Доступ владельца бессрочный.")
    if method in ("owner", "friend") and days is not None and not 1 <= days <= 365:
        raise ValueError("Срок для друга — от 1 до 365 дней или бессрочно.")
    if method in PAYMENT_METHODS and days not in (1, 3, 7):
        raise ValueError("Для оплаты доступны тарифы 1, 3 и 7 дней.")
    if method in PAYMENT_METHODS and reconciled is not True:
        raise ValueError("Подтвердите личную проверку поступления денег или завершённого обмена.")
    return installation, days, method


class OwnerWindow(ttk.Frame):
    def __init__(self, root: tk.Tk):
        super().__init__(root, padding=22)
        self.root, self.directory = root, owner_directory()
        root.title("Fortnite Pirate Token — доступ владельца")
        root.geometry("690x720")
        root.minsize(600, 680)
        self.pack(fill="both", expand=True)
        self.columnconfigure(0, weight=1)
        self.installation = tk.StringVar()
        self.method = tk.StringVar(value=next(iter(METHODS)))
        self.days = tk.StringVar(value="Бессрочно")
        self.reference = tk.StringVar(value="issue-" + uuid.uuid4().hex[:16])
        self.password = tk.StringVar()
        self.reconciled = tk.BooleanVar(value=False)
        for field in (self.installation, self.days, self.reference):
            field.trace_add("write", self.reset_reconciliation)
        self.status = tk.StringVar()
        ttk.Label(self, text="Выдать доступ", font=("Segoe UI", 22, "bold")).grid(sticky="w")
        ttk.Label(self, text="Только для владельца. Эту программу и приватную папку не передавайте клиентам.",
                  wraplength=620).grid(sticky="w", pady=(6, 16))
        self.key_label = ttk.Label(self, wraplength=620)
        self.key_label.grid(sticky="w")
        actions = ttk.Frame(self)
        actions.grid(sticky="ew", pady=(8, 15))
        ttk.Button(actions, text="Подготовить ключи", command=self.initialize).pack(side="left")
        ttk.Button(actions, text="Папка владельца", command=self.open_directory).pack(side="left", padx=8)
        self.field("Код установки получателя", self.installation)
        ttk.Label(self, text="Основание выдачи").grid(sticky="w", pady=(10, 4))
        method_box = ttk.Combobox(self, textvariable=self.method, values=list(METHODS), state="readonly")
        method_box.grid(sticky="ew")
        method_box.bind("<<ComboboxSelected>>", self.method_changed)
        ttk.Label(self, text="Срок действия").grid(sticky="w", pady=(10, 4))
        self.day_box = ttk.Combobox(self, textvariable=self.days, values=("Бессрочно",), state="readonly")
        self.day_box.grid(sticky="ew")
        self.reference_label = ttk.Label(self, text="Номер выдачи доступа")
        self.reference_label.grid(sticky="w", pady=(10, 4))
        ttk.Entry(self, textvariable=self.reference).grid(sticky="ew")
        self.field("Пароль приватного ключа", self.password, show="●")
        self.activation = ""
        self.reconcile_checkbox = ttk.Checkbutton(
            self, text="Я лично сверил заявку с поступлением или завершённым обменом",
            variable=self.reconciled, state="disabled",
        )
        self.reconcile_checkbox.grid(sticky="w", pady=(14, 6))
        ttk.Label(self, text="Скриншот оплаты или нажатие «Я оплатил» не подтверждают поступление.\n"
                  "Утилита не выполняет переводы и не проверяет Steam автоматически.",
                  wraplength=620).grid(sticky="w", pady=(0, 12))
        ttk.Button(self, text="Выдать и сохранить файл доступа…", command=self.issue).grid(sticky="ew")
        ttk.Button(self, text="Копировать последний код доступа", command=self.copy_code).grid(sticky="ew", pady=(8, 0))
        ttk.Label(self, textvariable=self.status, wraplength=620).grid(sticky="w", pady=(14, 0))
        self.refresh_keys()

    def field(self, label, variable, **kwargs):
        ttk.Label(self, text=label).grid(sticky="w", pady=(10, 4))
        ttk.Entry(self, textvariable=variable, **kwargs).grid(sticky="ew")

    def refresh_keys(self):
        ready = (self.directory / PRIVATE_KEY_NAME).is_file() and (self.directory / PUBLIC_KEY_NAME).is_file()
        self.key_label.configure(text=("Ключи готовы. " if ready else "Ключи ещё не подготовлены. ") + str(self.directory))

    def method_changed(self, _event=None):
        method = METHODS[self.method.get()]
        paid = method in PAYMENT_METHODS
        choices = ("1", "3", "7") if paid else (("Бессрочно",) if method == "owner"
                     else ("Бессрочно", "1", "3", "7", "30"))
        self.day_box.configure(state="readonly", values=choices)
        if self.days.get() not in choices:
            self.days.set("7" if paid else "Бессрочно")
        self.reference_label.configure(
            text="Номер перевода из выписки или ID Steam-обмена" if paid else "Номер выдачи доступа",
        )
        self.reference.set("" if paid else "issue-" + uuid.uuid4().hex[:16])
        self.reconcile_checkbox.configure(state="normal" if paid else "disabled")

    def reset_reconciliation(self, *_):
        self.reconciled.set(False)

    def open_directory(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        os.startfile(str(self.directory))

    def initialize(self):
        if (self.directory / PRIVATE_KEY_NAME).exists() or (self.directory / PUBLIC_KEY_NAME).exists():
            messagebox.showinfo("Ключи уже существуют", "Повторное создание отменено: старые лицензии должны продолжить работать.", parent=self.root)
            return
        password = simpledialog.askstring("Новый пароль", "Придумайте пароль приватного ключа (минимум 12 символов):", show="●", parent=self.root)
        if password is None:
            return
        confirm = simpledialog.askstring("Повтор пароля", "Повторите пароль:", show="●", parent=self.root)
        if confirm is None:
            return
        if password != confirm or len(password) < 12:
            messagebox.showerror("Пароль", "Пароли должны совпадать и содержать не менее 12 символов.", parent=self.root)
            return
        try:
            public = initialize_keys(self.directory, password.encode("utf-8"))
            self.refresh_keys()
            messagebox.showinfo("Ключи подготовлены", "Сохраните пароль и резервную копию приватной папки.\n\n"
                "Для сборки лаунчера нужен только этот публичный файл:\n" + str(public) +
                "\n\nЕго необходимо включить в assets/license-public.pem. Уже собранный клиент с другим ключом новые лицензии не примет.", parent=self.root)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Не удалось создать ключи", str(exc), parent=self.root)
        finally:
            password = confirm = None

    def copy_code(self):
        if not self.activation:
            messagebox.showinfo("Код", "Сначала выдайте лицензию.", parent=self.root)
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.activation)
        self.status.set("Код доступа скопирован. Передайте его получателю, но не приватный ключ.")

    def issue(self):
        try:
            installation, days, method = validate_request(self.installation.get(), self.days.get(), self.method.get(), self.reconciled.get())
            if not self.password.get():
                raise ValueError("Введите пароль приватного ключа.")
            reference = self.reference.get().strip()
            if not REFERENCE.fullmatch(reference):
                raise ValueError("Укажите номер операции или выдачи. Допустимы 4–128 знаков: латиница, цифры и _ . : -")
            if not (self.directory / PRIVATE_KEY_NAME).is_file():
                raise ValueError("Сначала подготовьте ключи владельца.")
            output = filedialog.asksaveasfilename(parent=self.root, title="Сохранить файл доступа для получателя",
                defaultextension=".json", initialfile="Fortnite-Pirate-Token-access.json", filetypes=[("Файл доступа", "*.json")])
            if not output:
                return
            target = Path(output).resolve()
            if target.is_relative_to(self.directory.resolve()):
                raise ValueError("Сохраняйте файлы получателей за пределами приватной папки владельца.")
            # Owner credentials must never be selected as the delivery file.
            if target.name in (PRIVATE_KEY_NAME, PUBLIC_KEY_NAME, "issued-licenses.sqlite3"):
                raise ValueError("Выберите отдельный JSON-файл для получателя.")
            document = issue_license(self.directory, installation, days, method, reference,
                password=self.password.get().encode("utf-8"), reconciled=self.reconciled.get())
            save_license(target, document)
            expiry = ("бессрочно" if document["payload"]["expires_at"] is None
                      else datetime.fromtimestamp(document["payload"]["expires_at"]).strftime("%d.%m.%Y %H:%M"))
            self.activation = activation_code(document)
            if method in PAYMENT_METHODS:
                self.reconciled.set(False)
            else:
                self.reference.set("issue-" + uuid.uuid4().hex[:16])
            self.status.set("Файл сохранён: " + str(target) + "\nДоступ: " + expiry + ". Можно передать JSON или скопировать код.")
            messagebox.showinfo("Доступ выдан", "Отправьте получателю JSON-файл или скопируйте код кнопкой выше.\n"
                "В лаунчере: Подписка → Вставить код → Активировать доступ.\n\n"
                "Никому не передавайте приватный ключ и админ-панель.", parent=self.root)
        except (OSError, ValueError, TypeError, sqlite3.Error) as exc:
            self.status.set("Выдача не завершена. Сохраняйте номер операции для безопасного повтора.")
            messagebox.showerror("Не удалось выдать доступ", str(exc), parent=self.root)
        finally:
            self.password.set("")


def main():
    root = tk.Tk()
    OwnerWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
