"""AI Panel widget for BlueP.

Chat interface for the AI agent - mirrors an AI assistant sidebar.

Features:
- Message history display (user/assistant/system messages)
- Input field with send button
- Async message sending (non-blocking)
- Tool execution status display
- Connection to AIAgent via chat_async()

Controlled by BLUEP_AI_ENABLED in .env. When disabled, shows a
placeholder message instead of the chat interface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, GLib, GObject, Pango

from bluep.core.ai_agent import AIAgent, AIMessage


class AIPanel(Gtk.Box):
    """AI agent chat panel - an AI assistant sidebar.

    When AI is enabled (BLUEP_AI_ENABLED=true), provides a full chat
    interface where the user can ask the AI to perform IDE actions:
    create classes, compile code, instantiate objects, etc.

    When disabled, shows a message explaining how to enable AI.
    """

    __gsignals__ = {
        "message-sent": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "message-received": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, agent: AIAgent | None = None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.agent = agent
        self.add_css_class("bluep-ai-panel")

        self._messages: list[tuple[str, str]] = []  # (role, content)
        self._is_processing = False
        self._poll_timeout_id = 0
        self._poll_start_time = 0.0
        self._history: list[str] = []
        self._history_index: int = -1

        # --- Header ---
        header_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 8)
        header_box.set_margin_start(8)
        header_box.set_margin_end(8)
        header_box.set_margin_top(8)
        header_box.set_margin_bottom(8)

        title = Gtk.Label.new("AI Assistant")
        title.add_css_class("bluep-class-name")
        title.set_hexpand(True)
        title.set_halign(Gtk.Align.START)
        header_box.append(title)

        self._status_indicator = Gtk.Label.new("")
        self._status_indicator.add_css_class("bluep-status-bar")
        header_box.append(self._status_indicator)

        self._btn_clear = Gtk.Button.new_from_icon_name("edit-clear-all")
        self._btn_clear.set_tooltip_text("Clear conversation")
        self._btn_clear.connect("clicked", lambda b: self.clear_conversation())
        header_box.append(self._btn_clear)

        self.append(header_box)
        self.append(Gtk.Separator.new(Gtk.Orientation.HORIZONTAL))

        if agent and agent.is_enabled:
            self._build_chat_interface()
            self._set_status("Ready")
        else:
            self._build_disabled_view()

    def _build_chat_interface(self) -> None:
        """Build the full chat interface for when AI is enabled."""
        # --- Message history ---
        self._message_scroll = Gtk.ScrolledWindow.new()
        self._message_scroll.set_vexpand(True)
        self._message_scroll.set_hexpand(True)

        self._message_list = Gtk.Box.new(Gtk.Orientation.VERTICAL, 4)
        self._message_list.set_margin_start(4)
        self._message_list.set_margin_end(4)
        self._message_list.set_margin_top(4)
        self._message_list.set_margin_bottom(4)
        self._message_scroll.set_child(self._message_list)

        self.append(self._message_scroll)

        # Welcome message
        self._add_message("system", "AI Assistant is ready. Ask me to create classes, "
                             "compile code, instantiate objects, inspect state, or anything else "
                             "you can do in the IDE.")

        # --- Separator ---
        self.append(Gtk.Separator.new(Gtk.Orientation.HORIZONTAL))

        # --- Input area ---
        input_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 4)
        input_box.set_margin_start(8)
        input_box.set_margin_end(8)
        input_box.set_margin_top(4)
        input_box.set_margin_bottom(4)

        self._input = Gtk.TextView.new()
        self._input.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self._input.set_top_margin(6)
        self._input.set_bottom_margin(6)
        self._input.set_left_margin(6)
        self._input.set_right_margin(6)
        self._input.set_hexpand(True)
        self._input.set_size_request(-1, 36)

        key_ctrl = Gtk.EventControllerKey.new()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self._input.add_controller(key_ctrl)

        input_scroll = Gtk.ScrolledWindow.new()
        input_scroll.set_child(self._input)
        input_scroll.set_hexpand(True)
        input_scroll.set_size_request(-1, 36)
        input_box.append(input_scroll)

        self._btn_send = Gtk.Button.new_with_label("Send")
        self._btn_send.add_css_class("bluep-btn-primary")
        self._btn_send.connect("clicked", lambda b: self._send_message())
        input_box.append(self._btn_send)

        self.append(input_box)

        # Focus input
        GLib.idle_add(lambda: self._input.grab_focus() and False)

    def _build_disabled_view(self) -> None:
        """Build the disabled placeholder view."""
        center_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 12)
        center_box.set_halign(Gtk.Align.CENTER)
        center_box.set_valign(Gtk.Align.CENTER)
        center_box.set_hexpand(True)
        center_box.set_vexpand(True)

        icon = Gtk.Image.new_from_icon_name("system-search")
        icon.set_pixel_size(48)
        center_box.append(icon)

        title = Gtk.Label.new("AI Assistant Disabled")
        title.add_css_class("bluep-class-name")
        center_box.append(title)

        info = Gtk.Label.new(
            "Enable AI by setting BLUEP_AI_ENABLED=true in your .env file.\n"
            "You'll also need to configure BLUEP_AI_API_KEY."
        )
        info.set_halign(Gtk.Align.CENTER)
        info.set_justify(Gtk.Justification.CENTER)
        info.set_wrap(True)
        info.add_css_class("bluep-status-bar")
        center_box.append(info)

        self.append(center_box)

    def set_agent(self, agent: AIAgent) -> None:
        """Set or update the AI agent."""
        self.agent = agent
        # Rebuild the panel
        # Remove all children
        child = self.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.remove(child)
            child = next_child

        # Rebuild header
        header_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 8)
        header_box.set_margin_start(8)
        header_box.set_margin_end(8)
        header_box.set_margin_top(8)
        header_box.set_margin_bottom(8)

        title = Gtk.Label.new("AI Assistant")
        title.add_css_class("bluep-class-name")
        title.set_hexpand(True)
        title.set_halign(Gtk.Align.START)
        header_box.append(title)

        self._status_indicator = Gtk.Label.new("")
        self._status_indicator.add_css_class("bluep-status-bar")
        header_box.append(self._status_indicator)

        self._btn_clear = Gtk.Button.new_from_icon_name("edit-clear-all")
        self._btn_clear.set_tooltip_text("Clear conversation")
        self._btn_clear.connect("clicked", lambda b: self.clear_conversation())
        header_box.append(self._btn_clear)

        self.append(header_box)
        self.append(Gtk.Separator.new(Gtk.Orientation.HORIZONTAL))

        if agent.is_enabled:
            self._build_chat_interface()
            self._set_status("Ready")
        else:
            self._build_disabled_view()

    def _add_message(self, role: str, content: str) -> None:
        """Add a message to the history display."""
        self._messages.append((role, content))

        if not hasattr(self, "_message_list"):
            return

        # Create message bubble
        bubble = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)

        if role == "user":
            bubble.add_css_class("bluep-ai-message-user")
            align = Gtk.Align.END
        elif role == "assistant":
            bubble.add_css_class("bluep-ai-message-assistant")
            align = Gtk.Align.START
        elif role == "error":
            bubble.add_css_class("bluep-ai-message-error")
            align = Gtk.Align.CENTER
        else:
            bubble.add_css_class("bluep-ai-message-system")
            align = Gtk.Align.CENTER

        bubble.set_halign(align)
        bubble.set_margin_start(4)
        bubble.set_margin_end(4)
        bubble.set_margin_top(2)
        bubble.set_margin_bottom(2)

        label = Gtk.Label.new(content)
        label.set_halign(Gtk.Align.START)
        label.set_xalign(0)
        label.set_wrap(True)
        label.set_selectable(True)
        label.set_max_width_chars(60)
        bubble.append(label)

        self._message_list.append(bubble)

        # Auto-scroll to bottom
        GLib.idle_add(self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> bool:
        """Scroll the message view to the bottom."""
        if hasattr(self, "_message_scroll"):
            adj = self._message_scroll.get_vadjustment()
            adj.set_value(adj.get_upper() - adj.get_page_size())
        return False

    def _on_key_pressed(self, controller: Gtk.EventControllerKey, keyval: int,
                        keycode: int, state: Gdk.ModifierType) -> bool:
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)

        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and not shift:
            self._send_message()
            return True

        if keyval == Gdk.KEY_Up and not shift:
            if self._history:
                if self._history_index < 0:
                    self._history_index = len(self._history)
                self._history_index = max(0, self._history_index - 1)
                self._input.get_buffer().set_text(self._history[self._history_index])
                return True

        if keyval == Gdk.KEY_Down and not shift:
            if self._history and self._history_index >= 0:
                self._history_index = min(len(self._history), self._history_index + 1)
                if self._history_index < len(self._history):
                    self._input.get_buffer().set_text(self._history[self._history_index])
                else:
                    self._input.get_buffer().set_text("")
                return True

        return False

    def _send_message(self) -> None:
        """Send the current input to the AI agent."""
        if self.agent is None or not self.agent.is_enabled:
            return

        if self.agent.is_running():
            return  # Don't send while processing

        buffer = self._input.get_buffer()
        start = buffer.get_start_iter()
        end = buffer.get_end_iter()
        text = buffer.get_text(start, end, True).strip()

        if not text:
            return

        buffer.set_text("")

        self._add_message("user", text)
        self.emit("message-sent", text)

        self._history.append(text)
        self._history_index = -1

        self._is_processing = True
        self._btn_send.set_sensitive(False)
        self._set_status("Thinking...")

        self.agent.set_message_callback(self._on_ai_message)
        try:
            self.agent.chat_async(text)
        except Exception as exc:
            self._abort_processing(f"Failed to send: {exc}")
            return

        import time
        self._poll_start_time = time.monotonic()
        self._poll_timeout_id = GLib.timeout_add(500, self._check_ai_completion)

    def _on_ai_message(self, message: str) -> None:
        """Callback for AI messages - runs in AI thread, so use idle_add."""
        GLib.idle_add(lambda: self._on_ai_message_idle(message))

    def _on_ai_message_idle(self, message: str) -> bool:
        """Handle AI message in the main thread."""
        if message.startswith("[AI executing:"):
            # Tool execution status
            self._add_message("system", message)
        else:
            # Regular AI response
            self._add_message("assistant", message)
            self.emit("message-received", message)
        return False

    def _check_ai_completion(self) -> bool:
        if self.agent is None:
            self._is_processing = False
            self._poll_timeout_id = 0
            return False

        import time
        elapsed = time.monotonic() - self._poll_start_time
        if elapsed > 120.0:
            self._abort_processing("Request timed out (120s)")
            return False

        if not self.agent.is_running():
            self._is_processing = False
            self._poll_timeout_id = 0
            self._btn_send.set_sensitive(True)
            self._set_status("Ready")
            self._input.grab_focus()
            return False

        return True

    def _abort_processing(self, reason: str) -> None:
        self._is_processing = False
        self._poll_timeout_id = 0
        self._btn_send.set_sensitive(True)
        self._set_status("Error")
        self._add_message("error", f"[error] {reason}")
        self._input.grab_focus()

    def _set_status(self, status: str) -> None:
        """Update the status indicator."""
        if hasattr(self, "_status_indicator"):
            self._status_indicator.set_text(status)

    def clear_conversation(self) -> None:
        """Clear the conversation history."""
        if self.agent:
            self.agent.reset_conversation()
        self._messages.clear()

        if hasattr(self, "_message_list"):
            # Remove all message bubbles
            child = self._message_list.get_first_child()
            while child:
                next_child = child.get_next_sibling()
                self._message_list.remove(child)
                child = next_child

            self._add_message("system", "Conversation cleared.")

    def add_context_message(self, message: str) -> None:
        """Add a system/context message (e.g., tool execution status)."""
        self._add_message("system", message)
