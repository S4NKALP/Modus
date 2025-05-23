from fabric.widgets.button import Button
from fabric.widgets.label import Label
from fabric.hyprland.widgets import Language, HyprlandEvent, get_hyprland_connection


class LanguageWidget(Button):
    """Widget that displays the current keyboard layout."""
    
    def __init__(self, **kwargs):
        self.lang_label = Label(name="lang-label")
        super().__init__(
            name="language", h_align="center", v_align="center", 
            child=self.lang_label, **kwargs
        )
        
        self.conn = get_hyprland_connection()
        self.update_language()
        self.conn.connect("event::activelayout", self.update_language)
    
    def update_language(self, _=None, event: HyprlandEvent = None):
        """Update the language indicator based on Hyprland events."""
        lang = event.data[1] if event else Language().get_label()
        self.set_tooltip_text(lang)
        self.lang_label.set_label(lang[:2].lower()) 