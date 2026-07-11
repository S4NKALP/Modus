project('app-capture', 'c',
  version: '1.0',
  default_options: ['c_std=c11', 'warning_level=1']
)

# Dependencies
wayland_client      = dependency('wayland-client')
wayland_scanner_dep = dependency('wayland-scanner', native: true)
gobject             = dependency('gobject-2.0')
gtk3                = dependency('gtk+-3.0')
gir                 = dependency('gobject-introspection-1.0', required: true)
cairo_dep           = dependency('cairo')

wayland_scanner = find_program('wayland-scanner')

# Protocol XML files
# All must exist under protocols/ in the source tree:
#
#   hyprland-toplevel-export-v1.xml     (hyprwm/hyprland-protocols)
#   wlr-foreign-toplevel-management-unstable-v1.xml  (swaywm/wlr-protocols)
#   hyprland-toplevel-mapping-v1.xml    (hyprwm/hyprland-protocols)
#   ext-foreign-toplevel-list-v1.xml    (wayland-protocols staging)
#
hypr_export_xml  = files('protocols/hyprland-toplevel-export-v1.xml')
wlr_toplevel_xml = files('protocols/wlr-foreign-toplevel-management-unstable-v1.xml')
hypr_mapping_xml = files('protocols/hyprland-toplevel-mapping-v1.xml')
ext_toplevel_xml = files('protocols/ext-foreign-toplevel-list-v1.xml')

# Generate C bindings

# hyprland-toplevel-export: the capture protocol we call directly
hypr_export_client_h = custom_target('hypr-export-client-h',
  input: hypr_export_xml, output: 'hyprland-toplevel-export-v1.h',
  command: [wayland_scanner, 'client-header', '@INPUT@', '@OUTPUT@'],
)
hypr_export_private_c = custom_target('hypr-export-private-c',
  input: hypr_export_xml, output: 'hyprland-toplevel-export-v1.c',
  command: [wayland_scanner, 'private-code', '@INPUT@', '@OUTPUT@'],
)

# wlr-foreign-toplevel: used to enumerate live windows and pass handles to the
# export protocol's v2 request; also provides zwlr_foreign_toplevel_handle_v1_interface
# which hyprland-toplevel-export-v1.c references at link time.
wlr_toplevel_client_h = custom_target('wlr-toplevel-client-h',
  input: wlr_toplevel_xml, output: 'wlr-foreign-toplevel-management-unstable-v1.h',
  command: [wayland_scanner, 'client-header', '@INPUT@', '@OUTPUT@'],
)
wlr_toplevel_private_c = custom_target('wlr-toplevel-private-c',
  input: wlr_toplevel_xml, output: 'wlr-foreign-toplevel-management-unstable-v1.c',
  command: [wayland_scanner, 'private-code', '@INPUT@', '@OUTPUT@'],
)

# hyprland-toplevel-mapping: maps wlr handles → full 64-bit Hyprland addresses.
# Its generated .c references ext_foreign_toplevel_handle_v1_interface (below).
hypr_mapping_client_h = custom_target('hypr-mapping-client-h',
  input: hypr_mapping_xml, output: 'hyprland-toplevel-mapping-v1.h',
  command: [wayland_scanner, 'client-header', '@INPUT@', '@OUTPUT@'],
)
hypr_mapping_private_c = custom_target('hypr-mapping-private-c',
  input: hypr_mapping_xml, output: 'hyprland-toplevel-mapping-v1.c',
  command: [wayland_scanner, 'private-code', '@INPUT@', '@OUTPUT@'],
)

# ext-foreign-toplevel-list: we never call it directly, but its private-code
# provides ext_foreign_toplevel_handle_v1_interface which the mapping protocol's
# generated .c references at link time.
ext_toplevel_private_c = custom_target('ext-toplevel-private-c',
  input: ext_toplevel_xml, output: 'ext-foreign-toplevel-list-v1.c',
  command: [wayland_scanner, 'private-code', '@INPUT@', '@OUTPUT@'],
)

# Shared library
lib = shared_library('appcapture',
  sources: [
    'app-capture.c',
    hypr_export_private_c,
    hypr_export_client_h,
    wlr_toplevel_private_c,
    wlr_toplevel_client_h,
    hypr_mapping_private_c,
    hypr_mapping_client_h,
    ext_toplevel_private_c,   # link-time symbol only, no header needed in our code
  ],
  include_directories: [
    include_directories('.'),
  ],
  dependencies: [
    wayland_client,
    gobject,
    gtk3,
    cairo_dep,
  ],
  gnu_symbol_visibility: 'default',
  install: true,
)

# GObject Introspection
gir_file = files('AppCapture-1.0.gir')

install_data(gir_file,
  install_dir: get_option('datadir') / 'gir-1.0',
)

gir_compiler = find_program('g-ir-compiler')

custom_target('appcapture-typelib',
  input:   gir_file,
  output:  'AppCapture-1.0.typelib',
  command: [gir_compiler, '--output=@OUTPUT@', '@INPUT@'],
  install: true,
  install_dir: get_option('libdir') / 'girepository-1.0',
)
