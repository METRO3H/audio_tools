import customtkinter as ctk


class LogPanel(ctk.CTkToplevel):

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.title("Logs")
        self.geometry("700x400")
        self.protocol("WM_DELETE_WINDOW", self.hide)
        self.withdraw()
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.textbox = ctk.CTkTextbox(self, state="disabled", wrap="word")
        self.textbox.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

    def append(self, text: str) -> None:
        self.textbox.configure(state="normal")
        self.textbox.insert("end", text + "\n")
        self.textbox.see("end")
        self.textbox.configure(state="disabled")

    def clear(self) -> None:
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.configure(state="disabled")

    def show(self) -> None:
        self.deiconify()
        self.lift()

    def hide(self) -> None:
        self.withdraw()

    def toggle(self) -> None:
        if self.winfo_viewable():
            self.hide()
        else:
            self.show()