"""Terminal UI — Textual app with five tabs and keybindings.

Excluded from coverage (it's I/O-heavy and tested manually via `demo.py`).
The whole TUI talks to the Daemon object directly — no IPC layer. If we ever
move the daemon out-of-process, swap this for an IPC client.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Iterable

from textual.app import App, ComposeResult  # type: ignore[import-not-found]
from textual.binding import Binding  # type: ignore[import-not-found]
from textual.containers import Container, Horizontal, Vertical  # type: ignore[import-not-found]
from textual.screen import ModalScreen  # type: ignore[import-not-found]
from textual.widgets import (  # type: ignore[import-not-found]
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Log,
    Static,
    TabbedContent,
    TabPane,
)

from netwatch.daemon import Daemon


def _fmt_ts(epoch: float) -> str:
    if not epoch:
        return "-"
    return datetime.fromtimestamp(epoch).strftime("%H:%M:%S")


class UnlockModal(ModalScreen[str]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        yield Container(
            Label("[bold red]SYSTEM LOCKED[/bold red] — enter unlock password"),
            Input(password=True, id="pw"),
            id="unlock-modal",
        )

    def on_input_submitted(self, message: Input.Submitted) -> None:
        self.dismiss(message.value)

    def action_cancel(self) -> None:
        self.dismiss("")


class NetwatchApp(App[None]):
    CSS = """
    Screen { layout: vertical; }
    #status-banner { dock: top; height: 3; padding: 1; }
    .locked { background: red; color: white; text-style: bold; }
    .ok { background: green; color: black; }
    DataTable { height: 1fr; }
    #unlock-modal { padding: 2; border: heavy red; width: 60; height: 7; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("b", "rebuild_baseline", "Rebuild baseline"),
        Binding("f", "force_freeze", "Force freeze"),
        Binding("u", "prompt_unlock", "Unlock"),
        Binding("question_mark", "show_help", "Help"),
    ]

    def __init__(self, daemon: Daemon):
        super().__init__()
        self.daemon = daemon

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(self._banner_text(), id="status-banner")
        with TabbedContent(initial="status"):
            with TabPane("Status [s]", id="status"):
                yield Static(id="status-body")
            with TabPane("Devices [d]", id="devices"):
                yield DataTable(id="devices-table")
            with TabPane("Alerts [a]", id="alerts"):
                yield DataTable(id="alerts-table")
            with TabPane("Whitelist [w]", id="whitelist"):
                yield Vertical(
                    Horizontal(Input(placeholder="MAC", id="wl-mac"), Label(" Enter to add", id="wl-hint")),
                    DataTable(id="wl-table"),
                )
            with TabPane("Logs [l]", id="logs"):
                yield Log(id="log-view", highlight=False)
        yield Footer()

    # ------------------------------------------------------- lifecycle hooks
    async def on_mount(self) -> None:
        for tid, cols in [
            ("devices-table", ("MAC", "Vendor", "Last IP", "Iface", "First seen", "Last seen")),
            ("alerts-table", ("When", "MAC", "Vendor", "IP", "Source")),
            ("wl-table", ("MAC",)),
        ]:
            tbl = self.query_one(f"#{tid}", DataTable)
            tbl.add_columns(*cols)
        self.set_interval(1.0, self._refresh)
        self.set_interval(0.25, self._drain_events)

    # ----------------------------------------------------------- refreshers
    def _banner_text(self) -> str:
        st = self.daemon.state.status_dict()
        if st["locked"]:
            return f"[bold red]LOCKED[/bold red] reason={st['lock_reason']}"
        if st["learning"]:
            return f"[yellow]LEARNING[/yellow] baseline={st['baseline_size']}"
        return f"[green]OK[/green] baseline={st['baseline_size']} alerts={st['alerts']}"

    def _refresh(self) -> None:
        self.query_one("#status-banner", Static).update(self._banner_text())
        self.query_one("#status-body", Static).update(self._status_body())
        self._refresh_devices()
        self._refresh_alerts()
        self._refresh_whitelist()

    def _status_body(self) -> str:
        st = self.daemon.state.status_dict()
        rows = "\n".join(f"  {k:<18} {v}" for k, v in st.items())
        return f"[bold]netwatch daemon[/bold]\n\n{rows}"

    def _refresh_devices(self) -> None:
        tbl = self.query_one("#devices-table", DataTable)
        tbl.clear()
        for d in self.daemon.baseline.devices.values():
            tbl.add_row(d.mac, d.vendor, d.last_ip or "-", d.iface or "-", d.first_seen, d.last_seen)

    def _refresh_alerts(self) -> None:
        tbl = self.query_one("#alerts-table", DataTable)
        tbl.clear()
        for a in list(self.daemon.state.alerts)[-50:]:
            tbl.add_row(_fmt_ts(a.timestamp), a.mac, a.vendor, a.ip or "-", a.source)

    def _refresh_whitelist(self) -> None:
        tbl = self.query_one("#wl-table", DataTable)
        tbl.clear()
        for mac in sorted(self.daemon.baseline.whitelist):
            tbl.add_row(mac)

    def _drain_events(self) -> None:
        log = self.query_one("#log-view", Log)
        for _ in range(20):
            try:
                ev = self.daemon.state.event_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            log.write_line(f"{ev.timestamp} {ev.type.value:<18} {ev.message}")

    # ---------------------------------------------------------------- actions
    def action_rebuild_baseline(self) -> None:
        self.daemon.rebuild_baseline()

    def action_force_freeze(self) -> None:
        self.daemon.force_freeze()

    def action_show_help(self) -> None:
        self.notify("q quit | b rebuild | f freeze | u unlock | tabs s/d/a/w/l")

    async def action_prompt_unlock(self) -> None:
        pw = await self.push_screen_wait(UnlockModal())
        if pw:
            result = self.daemon.unlock(pw)
            self.notify(("unlocked" if result.ok else f"denied: {result.reason}"),
                        severity="information" if result.ok else "error")

    def on_input_submitted(self, message: Input.Submitted) -> None:
        if message.input.id == "wl-mac":
            mac = message.value.strip()
            if mac:
                ok = self.daemon.add_whitelist(mac)
                self.notify(("whitelisted " + mac) if ok else "bad MAC", severity="information" if ok else "error")
            message.input.value = ""
