#define _GNU_SOURCE
#include "app-capture.h"

#include <wayland-client.h>
#include <gdk/gdkwayland.h>
#include <sys/mman.h>
#include <unistd.h>
#include <stdio.h>
#include <string.h>
#include <inttypes.h>

#include "hyprland-toplevel-export-v1.h"
#include "wlr-foreign-toplevel-management-unstable-v1.h"
#include "hyprland-toplevel-mapping-v1.h"

/* =========================================================================
 * Signals
 * ========================================================================= */

enum {
    SIGNAL_FRAME_READY,
    SIGNAL_FRAME_FAILED,
    LAST_SIGNAL
};

static guint signals[LAST_SIGNAL] = { 0 };

/* How long capture_by_handle() will wait for an unknown address's wlr handle
 * to arrive before giving up and emitting frame-failed. */
#define PENDING_CAPTURE_TIMEOUT_MS 1500

/* =========================================================================
 * Toplevel entry — one per live wlr toplevel
 * =========================================================================
 * We build a table of these at init time by:
 *   1. Binding zwlr_foreign_toplevel_manager_v1 and receiving toplevel events
 *   2. For each handle, requesting a hyprland_toplevel_mapping to get the
 *      full 64-bit Hyprland address (split as hi + lo uint32s)
 * This lets capture_by_handle() look up the wlr object for any address.
 * ========================================================================= */

typedef struct {
    struct zwlr_foreign_toplevel_handle_v1 *wlr_handle;
    char address[32];   /* hex string, e.g. "564f60266bd0", no "0x" prefix */
    gboolean mapped;    /* false until window_address event arrives */
} ToplevelEntry;

/* =========================================================================
 * Pending capture — capture_by_handle() called before mapping arrived
 * ========================================================================= */

typedef struct {
    AppCapture *self;       /* unowned; pending queue is owned by self */
    char       *address;    /* owned, stripped of "0x" */
    guint       timeout_id; /* 0 once consumed */
} PendingCapture;

/* =========================================================================
 * Object struct
 * ========================================================================= */

struct _AppCapture {
    GObject parent_instance;

    /* Wayland globals */
    struct wl_display                          *display;
    struct wl_registry                         *registry;
    struct wl_shm                              *shm;
    struct hyprland_toplevel_export_manager_v1 *export_manager;
    struct zwlr_foreign_toplevel_manager_v1    *wlr_manager;
    struct hyprland_toplevel_mapping_manager_v1 *mapping_manager;

    /* Address → wlr_handle table */
    GPtrArray *toplevels;        /* element-type: ToplevelEntry* */

    /* Captures waiting on a not-yet-mapped address */
    GPtrArray *pending_captures; /* element-type: PendingCapture* */

    /* Per-frame state — reset before every capture */
    int            shm_fd;
    unsigned char *pixel_data;
    uint32_t       width;
    uint32_t       height;
    uint32_t       stride;
    uint32_t       format;
    size_t         shm_size;
};

G_DEFINE_TYPE(AppCapture, app_capture, G_TYPE_OBJECT)

/* =========================================================================
 * Forward declarations
 * ========================================================================= */

static void     cleanup_shm(AppCapture *self);
static void     request_mapping(AppCapture *self, ToplevelEntry *entry);
static void     emit_frame_failed(AppCapture *self, const char *reason);
static void     do_capture(AppCapture *self,
                           struct zwlr_foreign_toplevel_handle_v1 *wlr_handle);
static struct zwlr_foreign_toplevel_handle_v1 *find_wlr_handle(AppCapture *self,
                                                               const char *addr);
static void     flush_pending_for_address(AppCapture *self, const char *address);
static gboolean pending_capture_timeout_cb(gpointer data);
static void     pending_capture_free(gpointer data);

/* =========================================================================
 * Hyprland toplevel mapping listener
 * Fires once per ToplevelEntry with the full 64-bit address.
 * ========================================================================= */

typedef struct {
    AppCapture    *self;
    ToplevelEntry *entry;
} MappingContext;

static void mapping_handle_window_address(void *data,
    struct hyprland_toplevel_window_mapping_handle_v1 *handle,
    uint32_t address_hi, uint32_t address)
{
    MappingContext *ctx = data;
    ToplevelEntry  *entry = ctx->entry;
    AppCapture     *self  = ctx->self;

    uint64_t full = ((uint64_t)address_hi << 32) | (uint64_t)address;
    snprintf(entry->address, sizeof(entry->address), "%" PRIx64, full);
    entry->mapped = TRUE;

    /* Dispatch any capture that was waiting for this address */
    flush_pending_for_address(self, entry->address);

    hyprland_toplevel_window_mapping_handle_v1_destroy(handle);
    g_free(ctx);
}

static void mapping_handle_failed(void *data,
    struct hyprland_toplevel_window_mapping_handle_v1 *handle)
{
    MappingContext *ctx = data;
    /* Address stays empty — this entry won't be matchable, which is fine.
     * Any pending capture for that address will time out via its own timer. */
    hyprland_toplevel_window_mapping_handle_v1_destroy(handle);
    g_free(ctx);
}

static const struct hyprland_toplevel_window_mapping_handle_v1_listener mapping_listener = {
    .window_address = mapping_handle_window_address,
    .failed         = mapping_handle_failed,
};

/* =========================================================================
 * wlr foreign toplevel listeners
 * We only need enough to know when a window appears or disappears.
 * ========================================================================= */

static void wlr_handle_title(void *data,
    struct zwlr_foreign_toplevel_handle_v1 *handle, const char *title)
{ (void)data; (void)handle; (void)title; }

static void wlr_handle_app_id(void *data,
    struct zwlr_foreign_toplevel_handle_v1 *handle, const char *app_id)
{ (void)data; (void)handle; (void)app_id; }

static void wlr_handle_output_enter(void *data,
    struct zwlr_foreign_toplevel_handle_v1 *handle, struct wl_output *output)
{ (void)data; (void)handle; (void)output; }

static void wlr_handle_output_leave(void *data,
    struct zwlr_foreign_toplevel_handle_v1 *handle, struct wl_output *output)
{ (void)data; (void)handle; (void)output; }

static void wlr_handle_state(void *data,
    struct zwlr_foreign_toplevel_handle_v1 *handle, struct wl_array *state)
{ (void)data; (void)handle; (void)state; }

static void wlr_handle_done(void *data,
    struct zwlr_foreign_toplevel_handle_v1 *handle)
{ (void)data; (void)handle; }

static void wlr_handle_closed(void *data,
    struct zwlr_foreign_toplevel_handle_v1 *handle)
{
    ToplevelEntry *entry = data;
    /* Mark as unmapped so capture_by_handle skips it */
    entry->mapped = FALSE;
    zwlr_foreign_toplevel_handle_v1_destroy(handle);
    entry->wlr_handle = NULL;
}

static void wlr_handle_parent(void *data,
    struct zwlr_foreign_toplevel_handle_v1 *handle,
    struct zwlr_foreign_toplevel_handle_v1 *parent)
{ (void)data; (void)handle; (void)parent; }

static const struct zwlr_foreign_toplevel_handle_v1_listener wlr_handle_listener = {
    .title        = wlr_handle_title,
    .app_id       = wlr_handle_app_id,
    .output_enter = wlr_handle_output_enter,
    .output_leave = wlr_handle_output_leave,
    .state        = wlr_handle_state,
    .done         = wlr_handle_done,
    .closed       = wlr_handle_closed,
    .parent       = wlr_handle_parent,
};

/* =========================================================================
 * wlr foreign toplevel manager listener
 * ========================================================================= */

static void wlr_manager_handle_toplevel(void *data,
    struct zwlr_foreign_toplevel_manager_v1 *manager,
    struct zwlr_foreign_toplevel_handle_v1 *handle)
{
    (void)manager;
    AppCapture    *self  = APP_CAPTURE(data);
    ToplevelEntry *entry = g_new0(ToplevelEntry, 1);
    entry->wlr_handle = handle;
    entry->mapped     = FALSE;

    zwlr_foreign_toplevel_handle_v1_add_listener(handle,
        &wlr_handle_listener, entry);

    g_ptr_array_add(self->toplevels, entry);

    /* Immediately request the Hyprland address mapping for this handle */
    if (self->mapping_manager)
        request_mapping(self, entry);
}

static void wlr_manager_handle_finished(void *data,
    struct zwlr_foreign_toplevel_manager_v1 *manager)
{ (void)data; (void)manager; }

static const struct zwlr_foreign_toplevel_manager_v1_listener wlr_manager_listener = {
    .toplevel = wlr_manager_handle_toplevel,
    .finished = wlr_manager_handle_finished,
};

/* =========================================================================
 * Mapping helper — ask Hyprland for the address of a wlr handle
 * ========================================================================= */

static void request_mapping(AppCapture *self, ToplevelEntry *entry)
{
    MappingContext *ctx = g_new0(MappingContext, 1);
    ctx->self  = self;
    ctx->entry = entry;

    struct hyprland_toplevel_window_mapping_handle_v1 *mh =
        hyprland_toplevel_mapping_manager_v1_get_window_for_toplevel_wlr(
            self->mapping_manager, entry->wlr_handle);

    hyprland_toplevel_window_mapping_handle_v1_add_listener(mh,
        &mapping_listener, ctx);
}

/* =========================================================================
 * Registry listener
 * ========================================================================= */

static void registry_handle_global(void *data, struct wl_registry *registry,
    uint32_t name, const char *interface, uint32_t version)
{
    (void)version;
    AppCapture *self = APP_CAPTURE(data);

    if (g_strcmp0(interface,
            hyprland_toplevel_export_manager_v1_interface.name) == 0) {
        self->export_manager = wl_registry_bind(registry, name,
            &hyprland_toplevel_export_manager_v1_interface, 2);
    }
    else if (g_strcmp0(interface, wl_shm_interface.name) == 0) {
        self->shm = wl_registry_bind(registry, name, &wl_shm_interface, 1);
    }
    else if (g_strcmp0(interface,
            zwlr_foreign_toplevel_manager_v1_interface.name) == 0) {
        self->wlr_manager = wl_registry_bind(registry, name,
            &zwlr_foreign_toplevel_manager_v1_interface, 3);
        zwlr_foreign_toplevel_manager_v1_add_listener(self->wlr_manager,
            &wlr_manager_listener, self);
    }
    else if (g_strcmp0(interface,
            hyprland_toplevel_mapping_manager_v1_interface.name) == 0) {
        self->mapping_manager = wl_registry_bind(registry, name,
            &hyprland_toplevel_mapping_manager_v1_interface, 1);
    }
}

static void registry_handle_global_remove(void *data,
    struct wl_registry *registry, uint32_t name)
{ (void)data; (void)registry; (void)name; }

static const struct wl_registry_listener registry_listener = {
    .global        = registry_handle_global,
    .global_remove = registry_handle_global_remove,
};

/* =========================================================================
 * Frame listener
 *
 * Event order: buffer → (linux_dmabuf) → buffer_done → [copy()] → flags → ready|failed
 * ========================================================================= */

static void frame_handle_buffer(void *data,
    struct hyprland_toplevel_export_frame_v1 *frame,
    uint32_t format, uint32_t width, uint32_t height, uint32_t stride)
{
    (void)frame;
    AppCapture *self = APP_CAPTURE(data);
    self->format = format;
    self->width  = width;
    self->height = height;
    self->stride = stride;
}

static void frame_handle_linux_dmabuf(void *data,
    struct hyprland_toplevel_export_frame_v1 *frame,
    uint32_t format, uint32_t width, uint32_t height)
{ (void)data; (void)frame; (void)format; (void)width; (void)height; }

static void frame_handle_buffer_done(void *data,
    struct hyprland_toplevel_export_frame_v1 *frame)
{
    AppCapture *self = APP_CAPTURE(data);

    if (self->width == 0 || self->height == 0 || self->stride == 0) {
        g_warning("AppCapture: buffer_done with zero dimensions");
        hyprland_toplevel_export_frame_v1_destroy(frame);
        emit_frame_failed(self, "buffer_invalid");
        return;
    }

    self->shm_size = (size_t)self->stride * self->height;

    self->shm_fd = memfd_create("app-capture-buffer", 0);
    if (self->shm_fd < 0) {
        g_warning("AppCapture: memfd_create failed");
        hyprland_toplevel_export_frame_v1_destroy(frame);
        emit_frame_failed(self, "alloc_failed");
        return;
    }

    if (ftruncate(self->shm_fd, (off_t)self->shm_size) < 0) {
        g_warning("AppCapture: ftruncate failed");
        cleanup_shm(self);
        hyprland_toplevel_export_frame_v1_destroy(frame);
        emit_frame_failed(self, "alloc_failed");
        return;
    }

    self->pixel_data = mmap(NULL, self->shm_size,
                            PROT_READ | PROT_WRITE, MAP_SHARED,
                            self->shm_fd, 0);
    if (self->pixel_data == MAP_FAILED) {
        g_warning("AppCapture: mmap failed");
        self->pixel_data = NULL;
        cleanup_shm(self);
        hyprland_toplevel_export_frame_v1_destroy(frame);
        emit_frame_failed(self, "alloc_failed");
        return;
    }

    struct wl_shm_pool *pool = wl_shm_create_pool(self->shm, self->shm_fd,
                                                   (int32_t)self->shm_size);
    struct wl_buffer *buffer = wl_shm_pool_create_buffer(pool,
        0, (int32_t)self->width, (int32_t)self->height,
        (int32_t)self->stride, self->format);
    wl_shm_pool_destroy(pool);

    hyprland_toplevel_export_frame_v1_copy(frame, buffer, 1);
    wl_buffer_destroy(buffer);
}

static void frame_handle_flags(void *data,
    struct hyprland_toplevel_export_frame_v1 *frame, uint32_t flags)
{ (void)data; (void)frame; (void)flags; }

static void frame_handle_ready(void *data,
    struct hyprland_toplevel_export_frame_v1 *frame,
    uint32_t tv_sec_hi, uint32_t tv_sec_lo, uint32_t tv_nsec)
{
    (void)tv_sec_hi; (void)tv_sec_lo; (void)tv_nsec;
    AppCapture *self = APP_CAPTURE(data);

    if (!self->pixel_data) {
        g_warning("AppCapture: ready fired but pixel_data is NULL");
        hyprland_toplevel_export_frame_v1_destroy(frame);
        emit_frame_failed(self, "internal");
        return;
    }

    GBytes *bytes = g_bytes_new(self->pixel_data, self->shm_size);
    g_signal_emit(self, signals[SIGNAL_FRAME_READY], 0,
                  bytes, (gint)self->width, (gint)self->height, (gint)self->stride);
    g_bytes_unref(bytes);

    cleanup_shm(self);
    hyprland_toplevel_export_frame_v1_destroy(frame);
}

static void frame_handle_failed(void *data,
    struct hyprland_toplevel_export_frame_v1 *frame)
{
    AppCapture *self = APP_CAPTURE(data);
    g_warning("AppCapture: frame capture failed");
    cleanup_shm(self);
    hyprland_toplevel_export_frame_v1_destroy(frame);
    emit_frame_failed(self, "frame_failed");
}

static void frame_handle_damage(void *data,
    struct hyprland_toplevel_export_frame_v1 *frame,
    uint32_t x, uint32_t y, uint32_t width, uint32_t height)
{ (void)data; (void)frame; (void)x; (void)y; (void)width; (void)height; }

static const struct hyprland_toplevel_export_frame_v1_listener frame_listener = {
    .buffer       = frame_handle_buffer,
    .linux_dmabuf = frame_handle_linux_dmabuf,
    .buffer_done  = frame_handle_buffer_done,
    .flags        = frame_handle_flags,
    .ready        = frame_handle_ready,
    .failed       = frame_handle_failed,
    .damage       = frame_handle_damage,
};

/* =========================================================================
 * Capture helpers
 * ========================================================================= */

static void emit_frame_failed(AppCapture *self, const char *reason)
{
    g_signal_emit(self, signals[SIGNAL_FRAME_FAILED], 0, reason);
}

static struct zwlr_foreign_toplevel_handle_v1 *find_wlr_handle(AppCapture *self,
                                                               const char *addr)
{
    for (guint i = 0; i < self->toplevels->len; i++) {
        ToplevelEntry *entry = g_ptr_array_index(self->toplevels, i);
        if (entry->mapped && entry->wlr_handle &&
            g_strcmp0(entry->address, addr) == 0)
            return entry->wlr_handle;
    }
    return NULL;
}

static void do_capture(AppCapture *self,
                       struct zwlr_foreign_toplevel_handle_v1 *wlr_handle)
{
    self->width = self->height = self->stride = self->format = 0;

    struct hyprland_toplevel_export_frame_v1 *frame =
        hyprland_toplevel_export_manager_v1_capture_toplevel_with_wlr_toplevel_handle(
            self->export_manager,
            0,           /* overlay_cursor */
            wlr_handle
        );

    hyprland_toplevel_export_frame_v1_add_listener(frame, &frame_listener, self);
    wl_display_flush(self->display);
}

/* =========================================================================
 * Pending capture queue
 *
 * When capture_by_handle() is called for an address whose wlr handle hasn't
 * been mapped yet (race between Hyprland IPC and wlr foreign-toplevel), we
 * park a PendingCapture and wait for either:
 *   - mapping_handle_window_address → flush_pending_for_address → do_capture
 *   - PENDING_CAPTURE_TIMEOUT_MS elapses → emit frame-failed
 *
 * In practice the JS layer is single-flight so this queue holds ≤ 1 entry.
 * ========================================================================= */

static void pending_capture_free(gpointer data)
{
    PendingCapture *pc = data;
    if (pc->timeout_id != 0) {
        g_source_remove(pc->timeout_id);
        pc->timeout_id = 0;
    }
    g_free(pc->address);
    g_free(pc);
}

static gboolean pending_capture_timeout_cb(gpointer data)
{
    PendingCapture *pc   = data;
    AppCapture     *self = pc->self;

    g_warning("AppCapture: timeout waiting for wlr handle '%s' "
              "(toplevel table has %u entries)",
              pc->address, self->toplevels->len);

    /* Mark consumed so pending_capture_free doesn't double-remove */
    pc->timeout_id = 0;

    /* Remove first (frees pc), THEN emit — emit may re-enter capture_by_handle */
    g_ptr_array_remove(self->pending_captures, pc);
    emit_frame_failed(self, "no_handle_timeout");
    return G_SOURCE_REMOVE;
}

static void flush_pending_for_address(AppCapture *self, const char *address)
{
    if (self->pending_captures->len == 0) return;

    struct zwlr_foreign_toplevel_handle_v1 *wlr_handle =
        find_wlr_handle(self, address);
    if (!wlr_handle) return;

    /* Iterate backwards so removals don't shift indices we're about to visit */
    for (guint i = self->pending_captures->len; i > 0; i--) {
        PendingCapture *pc = g_ptr_array_index(self->pending_captures, i - 1);
        if (g_strcmp0(pc->address, address) != 0) continue;

        do_capture(self, wlr_handle);
        g_ptr_array_remove_index(self->pending_captures, i - 1);
        /* JS side is single-flight — at most one match expected.
         * Break to avoid issuing two captures against the same shm state. */
        break;
    }
}

/* =========================================================================
 * SHM helpers
 * ========================================================================= */

static void cleanup_shm(AppCapture *self)
{
    if (self->pixel_data && self->pixel_data != MAP_FAILED) {
        munmap(self->pixel_data, self->shm_size);
        self->pixel_data = NULL;
    }
    if (self->shm_fd >= 0) {
        close(self->shm_fd);
        self->shm_fd = -1;
    }
    self->shm_size = 0;
}

static void toplevel_entry_free(gpointer data)
{
    ToplevelEntry *entry = data;
    if (entry->wlr_handle)
        zwlr_foreign_toplevel_handle_v1_destroy(entry->wlr_handle);
    g_free(entry);
}

/* =========================================================================
 * GObject lifecycle
 * ========================================================================= */

static void app_capture_finalize(GObject *object)
{
    AppCapture *self = APP_CAPTURE(object);
    cleanup_shm(self);
    g_ptr_array_unref(self->pending_captures);
    g_ptr_array_unref(self->toplevels);
    if (self->export_manager)
        hyprland_toplevel_export_manager_v1_destroy(self->export_manager);
    if (self->mapping_manager)
        hyprland_toplevel_mapping_manager_v1_destroy(self->mapping_manager);
    if (self->wlr_manager)
        zwlr_foreign_toplevel_manager_v1_destroy(self->wlr_manager);
    if (self->shm)
        wl_shm_destroy(self->shm);
    if (self->registry)
        wl_registry_destroy(self->registry);
    G_OBJECT_CLASS(app_capture_parent_class)->finalize(object);
}

static void app_capture_class_init(AppCaptureClass *klass)
{
    GObjectClass *object_class = G_OBJECT_CLASS(klass);
    object_class->finalize = app_capture_finalize;

    signals[SIGNAL_FRAME_READY] = g_signal_new(
        "frame-ready",
        G_TYPE_FROM_CLASS(klass),
        G_SIGNAL_RUN_LAST,
        0, NULL, NULL, NULL,
        G_TYPE_NONE, 4,
        G_TYPE_BYTES, G_TYPE_INT, G_TYPE_INT, G_TYPE_INT
    );

    signals[SIGNAL_FRAME_FAILED] = g_signal_new(
        "frame-failed",
        G_TYPE_FROM_CLASS(klass),
        G_SIGNAL_RUN_LAST,
        0, NULL, NULL, NULL,
        G_TYPE_NONE, 1,
        G_TYPE_STRING
    );
}

static void app_capture_init(AppCapture *self)
{
    self->shm_fd           = -1;
    self->pixel_data       = NULL;
    self->shm_size         = 0;
    self->toplevels        = g_ptr_array_new_with_free_func(toplevel_entry_free);
    self->pending_captures = g_ptr_array_new_with_free_func(pending_capture_free);

    GdkDisplay *gdk_display = gdk_display_get_default();
    self->display = gdk_wayland_display_get_wl_display(gdk_display);

    self->registry = wl_display_get_registry(self->display);
    wl_registry_add_listener(self->registry, &registry_listener, self);

    /* First roundtrip: compositor advertises globals, we bind them all */
    wl_display_roundtrip(self->display);

    /* Second roundtrip: wlr_manager emits toplevel events for existing
     * windows, and mapping requests are sent for each one */
    wl_display_roundtrip(self->display);

    /* Third roundtrip: mapping responses (window_address events) arrive */
    wl_display_roundtrip(self->display);

    if (!self->export_manager)
        g_warning("AppCapture: hyprland_toplevel_export_manager_v1 not found");
    if (!self->wlr_manager)
        g_warning("AppCapture: zwlr_foreign_toplevel_manager_v1 not found");
    if (!self->mapping_manager)
        g_warning("AppCapture: hyprland_toplevel_mapping_manager_v1 not found");
    if (!self->shm)
        g_warning("AppCapture: wl_shm not found");
}

/* =========================================================================
 * Public API
 * ========================================================================= */

AppCapture *app_capture_new(void)
{
    return g_object_new(APP_TYPE_CAPTURE, NULL);
}

void app_capture_capture_by_handle(AppCapture *self, const gchar *address)
{
    g_return_if_fail(APP_IS_CAPTURE(self));
    g_return_if_fail(address != NULL);

    if (!self->export_manager) {
        g_warning("AppCapture: export_manager not available");
        emit_frame_failed(self, "no_export_manager");
        return;
    }

    /* Strip optional "0x" prefix so matching works regardless of input */
    const gchar *addr = address;
    if (g_str_has_prefix(addr, "0x") || g_str_has_prefix(addr, "0X"))
        addr += 2;

    /* Fast path: handle already known and mapped */
    struct zwlr_foreign_toplevel_handle_v1 *wlr_handle =
        find_wlr_handle(self, addr);
    if (wlr_handle) {
        do_capture(self, wlr_handle);
        return;
    }

    /* Slow path: park and wait up to PENDING_CAPTURE_TIMEOUT_MS for the
     * wlr_manager toplevel/mapping events to arrive. Race window is
     * typically <100 ms in practice but can spike under load. */
    PendingCapture *pc = g_new0(PendingCapture, 1);
    pc->self       = self;
    pc->address    = g_strdup(addr);
    pc->timeout_id = g_timeout_add(PENDING_CAPTURE_TIMEOUT_MS,
                                   pending_capture_timeout_cb, pc);
    g_ptr_array_add(self->pending_captures, pc);
}
