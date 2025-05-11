import json
from gi.repository import GLib, Gdk
from fabric.hyprland.widgets import get_hyprland_connection
from utils.occlusion import check_occlusion


class AutoHideBarController:
    """Controller for bar auto-hide behavior."""
    
    # Constants for configuration
    OCCLUSION_CHECK_INTERVAL = 250  # ms
    HIDE_DELAY = 300  # ms
    
    def __init__(self, bar):
        self.bar = bar
        self.is_hidden = False
        self.hide_id = None
        self.is_hovered = False
        self.conn = get_hyprland_connection()
        self.last_occlusion_state = False
        
        self._setup_event_handlers()
        self._start_occlusion_checking()
        
    def _setup_event_handlers(self):
        """Initialize event handlers for window management"""
        # Initial state check
        if self.conn.ready:
            self.check_hide()
        else:
            self.conn.connect("event::ready", lambda *_: self.check_hide())
            
        # Monitor window events
        window_events = ("activewindow", "openwindow", "closewindow", "changefloatingmode")
        for event in window_events:
            self.conn.connect(f"event::{event}", lambda *_: self.check_hide())
        self.conn.connect("event::workspace", lambda *_: GLib.timeout_add(50, self.check_hide))
    
    def _start_occlusion_checking(self):
        """Start periodic occlusion check"""
        GLib.timeout_add(self.OCCLUSION_CHECK_INTERVAL, self.check_occlusion_state)
    
    def _get_bar_height(self):
        """Get the height of the bar with fallback"""
        try:
            height = self.bar.get_allocated_height()
            return height if height > 0 else 30
        except Exception:
            return 30  # Default fallback
    
    def _get_occlusion_region(self):
        """Get the region to check for occlusion"""
        return ("top", self._get_bar_height())
    
    def check_occlusion_state(self):
        """Periodic occlusion check"""
        # Skip occlusion check if hovered
        if self.is_hovered:
            self.bar.main_box.remove_style_class("occluded")
            return True
            
        # Check occlusion using the top region
        is_occluded = check_occlusion(self._get_occlusion_region())
        
        # Only apply changes if state has changed to avoid unnecessary CSS operations
        if is_occluded != self.last_occlusion_state:
            self.last_occlusion_state = is_occluded
            if is_occluded:
                self.bar.main_box.add_style_class("occluded")
            else:
                self.bar.main_box.remove_style_class("occluded")
                if not self.is_hovered and self.is_hidden:
                    # Debounce showing the bar to prevent flickering
                    GLib.timeout_add(100, lambda: self.toggle_bar(not self._should_stay_hidden()))
        
        return True
        
    def _should_stay_hidden(self):
        """Determine if the bar should stay hidden based on window state"""
        clients = self.get_clients()
        current_ws = self.get_workspace()
        ws_clients = [w for w in clients if w["workspace"]["id"] == current_ws]
        
        # If we have normal windows and are not being hovered, stay hidden
        return self._has_normal_windows(ws_clients) and not self.is_hovered
        
    def on_bar_enter(self, widget, event):
        """Handle hover over bar content."""
        self.is_hovered = True
        self.bar.main_box.remove_style_class("occluded")
        
        # Cancel any pending hide operations
        self._cancel_hide_timer()
        self.toggle_bar(show=True)
        return True  # Stop event propagation
        
    def on_bar_leave(self, widget, event):
        """Handle leave from bar content."""
        # Only trigger if mouse actually left the entire bar area
        if event.detail == Gdk.NotifyType.INFERIOR:
            return False  # Ignore child-to-child mouse movements
            
        self.is_hovered = False
        
        # Schedule hide if needed
        if self._should_stay_hidden() or check_occlusion(self._get_occlusion_region()):
            self.delay_hide()
            
            # Update occlusion state
            if check_occlusion(self._get_occlusion_region()):
                self.last_occlusion_state = True
                self.bar.main_box.add_style_class("occluded")
            
        return True  # Stop event propagation
        
    def on_hover_enter(self, *args):
        """Handle hover over top activation area."""
        self.bar.main_box.remove_style_class("occluded")
        self.toggle_bar(show=True)
        return False
    
    def _cancel_hide_timer(self):
        """Cancel any pending hide timer"""
        if self.hide_id:
            GLib.source_remove(self.hide_id)
            self.hide_id = None
        
    def toggle_bar(self, show):
        """Show or hide the bar immediately."""
        if show:
            if self.is_hidden:
                self.is_hidden = False
                self.bar.main_box.remove_style_class("hide-bar")
                self.bar.main_box.add_style_class("show-bar")
            self._cancel_hide_timer()
        else:
            if not self.is_hidden:
                self.is_hidden = True
                self.bar.main_box.remove_style_class("show-bar")
                self.bar.main_box.add_style_class("hide-bar")
    
    def delay_hide(self):
        """Schedule hiding after short delay."""
        self._cancel_hide_timer()
        self.hide_id = GLib.timeout_add(self.HIDE_DELAY, self.hide_bar)
        
    def hide_bar(self):
        """Finalize hiding procedure."""
        if not self.is_hovered:
            self.toggle_bar(show=False)
        self.hide_id = None
        return False
    
    def get_clients(self):
        """Get current client list."""
        try:
            return json.loads(self.conn.send_command("j/clients").reply.decode())
        except (json.JSONDecodeError, AttributeError):
            return []
            
    def get_workspace(self):
        """Get current workspace ID."""
        try:
            return json.loads(
                self.conn.send_command("j/activeworkspace").reply.decode()
            ).get("id", 0)
        except (json.JSONDecodeError, AttributeError):
            return 0
    
    def _has_normal_windows(self, clients):
        """Check if any non-floating, non-fullscreen windows exist"""
        return any(not w.get("floating") and not w.get("fullscreen") for w in clients)
            
    def check_hide(self, *args):
        """Determine if bar should auto-hide based on window state."""
        # Get window data
        clients = self.get_clients()
        current_ws = self.get_workspace()
        ws_clients = [w for w in clients if w["workspace"]["id"] == current_ws]
        
        # Check for occlusion
        is_occluded = check_occlusion(self._get_occlusion_region())
        self.last_occlusion_state = is_occluded
        
        # Determine visibility state
        if not ws_clients:
            # No windows in current workspace, show the bar
            self.bar.main_box.remove_style_class("occluded")
            self.toggle_bar(show=True)
        elif self._has_normal_windows(ws_clients):
            # Normal windows exist, handle occlusion and hide if not hovered
            if is_occluded:
                self.bar.main_box.add_style_class("occluded")
            
            if not self.is_hovered:
                self.toggle_bar(show=False)
        else:
            # Only floating/fullscreen windows, show the bar
            self.bar.main_box.remove_style_class("occluded")
            self.toggle_bar(show=True)
            
        return False 