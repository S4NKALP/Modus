#define _GNU_SOURCE
#include <dlfcn.h>
#include <gtk/gtk.h>

typedef void (*orig_gtk_menu_item_activate)(GtkMenuItem *menu_item);

static int in_hook = 0;

typedef struct {
    GtkWidget *widget;
} WidgetRef;

static gboolean do_emit(gpointer data) {
    WidgetRef *ref = data;
    GtkWidget *w = ref->widget;
    g_free(ref);
    if (!GTK_IS_WIDGET(w))
        return G_SOURCE_REMOVE;

    GdkEvent event;
    memset(&event, 0, sizeof(event));
    event.type = GDK_BUTTON_RELEASE;
    event.any.window = gtk_widget_get_window(w);
    event.any.send_event = TRUE;

    gboolean handled = FALSE;
    g_signal_emit_by_name(w, "button-release-event", &event, &handled);
    return G_SOURCE_REMOVE;
}

void gtk_menu_item_activate(GtkMenuItem *menu_item) {
    if (in_hook) {
        orig_gtk_menu_item_activate orig =
            (orig_gtk_menu_item_activate)dlsym(RTLD_NEXT, "gtk_menu_item_activate");
        orig(menu_item);
        return;
    }
    in_hook = 1;

    orig_gtk_menu_item_activate orig =
        (orig_gtk_menu_item_activate)dlsym(RTLD_NEXT, "gtk_menu_item_activate");
    orig(menu_item);

    in_hook = 0;

    /* After real activate, schedule synthetic button-release-event so apps
       that connect to button-release-event instead of activate respond. */
    WidgetRef *ref = g_new(WidgetRef, 1);
    ref->widget = GTK_WIDGET(menu_item);
    g_timeout_add(50, do_emit, ref);
}
