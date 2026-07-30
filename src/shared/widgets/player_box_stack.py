from fabric.utils import bulk_connect, logger
from fabric.widgets.box import Box
from fabric.widgets.button import Button


class BasePlayerBoxStack(Box):
    def __init__(self, mpris_manager, **kwargs):
        super().__init__(
            orientation="v", name="media", children=[self.player_stack], **kwargs
        )
        self.player_stack.children = [self.no_media_box]
        self.set_visible(True)
        self.mpris_manager = mpris_manager
        self.connect("map", self._on_map)

        if self.mpris_manager is not None:
            self._init_signals()

    def _init_signals(self):
        try:
            connections = bulk_connect(
                self.mpris_manager,
                {
                    "new-player": self.on_new_player,
                    "player-vanish": self.on_lost_player,
                },
            )
            for handler_id in connections:
                self._signal_connections.append((self.mpris_manager, handler_id))

            for name, player in self.mpris_manager.get_all_services().items():
                self.on_new_player(self.mpris_manager, name, player)
        except Exception as e:
            logger.error(f"Failed to initialize PlayerBoxStack signals: {e}")

    def _on_map(self, *_):
        self._check_and_update_playing_state()

    def destroy(self):
        for obj, handler_id in self._signal_connections:
            try:
                obj.disconnect(handler_id)
            except Exception as e:
                logger.error(f"An error occurred: {e}")
        self._signal_connections.clear()
        super().destroy()

    def _find_playing_player_index(self):
        players = self.player_stack.get_children()
        for i, player_box in enumerate(players):
            if (
                hasattr(player_box, "player")
                and str(player_box.player.playback_status).lower() == "playing"
            ):
                return i
        return None

    def _check_and_update_playing_state(self):
        children = self.player_stack.get_children()
        players = [p for p in children if p != self.no_media_box]
        if len(players) > 0:
            if self.no_media_box in children:
                self.player_stack.remove(self.no_media_box)
            playing_index = self._find_playing_player_index()
            if playing_index is not None:
                self.on_player_clicked_by_index(playing_index)
            return

        if len(children) == 1 and children[0] == self.no_media_box:
            return

        self.player_stack.children = [self.no_media_box]
        self.current_stack_pos = 0
        self.player_stack.set_visible_child(self.no_media_box)

    def on_player_playback_changed(self, player_box, status):
        status = str(status).lower()
        if status == "playing":
            players = self.player_stack.get_children()
            for i, pb in enumerate(players):
                if pb == player_box and i != self.current_stack_pos:
                    self.on_player_clicked_by_index(i)
                    break
        elif status in ["paused", "stopped"]:
            self._check_and_update_playing_state()

    def _update_all_player_buttons(self):
        show_buttons = len(self.player_buttons) > 1
        for child in self.player_stack.get_children():
            if hasattr(child, "update_buttons"):
                child.update_buttons(self.player_buttons, show_buttons)

    def on_player_clicked_by_index(self, index):
        if 0 <= index < len(self.player_buttons):
            if self.current_stack_pos < len(self.player_buttons):
                self.player_buttons[self.current_stack_pos].remove_style_class("active")
            self.current_stack_pos = index
            self.player_buttons[self.current_stack_pos].add_style_class("active")
            self.player_stack.set_visible_child(
                self.player_stack.get_children()[self.current_stack_pos]
            )
            self._update_all_player_buttons()

    def on_new_player(self, mpris_manager, name, player):
        children = self.player_stack.get_children()
        if len(children) == 1 and children[0] == self.no_media_box:
            self.player_stack.children = []
            self.current_stack_pos = 0

        self.set_visible(True)
        new_player_box = self._create_player_box_widget(player)
        self.player_stack.children = [*self.player_stack.children, new_player_box]
        self.make_new_player_button(new_player_box)
        if self.player_buttons:
            self.player_buttons[self.current_stack_pos].set_style_classes(["active"])
        self._check_and_update_playing_state()
        self._update_all_player_buttons()

    def _create_player_box_widget(self, player):
        from window.controlcenter.player import PlayerBox

        return PlayerBox(player=player, player_stack=self)

    def on_lost_player(self, mpris_manager, bus_name):
        children = self.player_stack.get_children()
        player_box_to_remove = None
        for player_box in children:
            if (
                hasattr(player_box, "player")
                and getattr(player_box.player, "player_name", None) == bus_name
            ):
                player_box_to_remove = player_box
                break

        if player_box_to_remove:
            player_box_to_remove.destroy()

        remaining = [
            c for c in self.player_stack.get_children() if c != player_box_to_remove
        ]
        if len(remaining) == 0:
            self.player_stack.children = [self.no_media_box]
            self.current_stack_pos = 0
            self.player_buttons = []
            return

        if self.current_stack_pos >= len(remaining):
            self.current_stack_pos = max(0, len(remaining) - 1)

        if self.player_buttons and self.current_stack_pos < len(self.player_buttons):
            self.player_buttons[self.current_stack_pos].set_style_classes(["active"])
            self.player_stack.set_visible_child(remaining[self.current_stack_pos])
        self._update_all_player_buttons()

    def make_new_player_button(self, player_box):
        new_button = Button(name="player-stack-button")

        def on_player_button_click(button: Button):
            if self.current_stack_pos < len(self.player_buttons):
                self.player_buttons[self.current_stack_pos].remove_style_class("active")
            if button in self.player_buttons:
                self.current_stack_pos = self.player_buttons.index(button)
                button.add_style_class("active")
                self.player_stack.set_visible_child(player_box)

        new_button.connect("clicked", on_player_button_click)
        self.player_buttons.append(new_button)
        player_box.connect(
            "destroy",
            lambda *_: (
                self.player_buttons.remove(new_button)
                if new_button in self.player_buttons
                else None
            ),
        )

    def suspend(self):
        for child in self.player_stack.get_children():
            if hasattr(child, "suspend"):
                child.suspend()

    def resume(self):
        for child in self.player_stack.get_children():
            if hasattr(child, "resume"):
                child.resume()

    def _create_no_media_box(self):
        raise NotImplementedError
