#!/usr/bin/env python3
"""
Remap the requested country MU -> <TARGET> in the Broadcom bcmdhd driver.

WHY
---
This radio is regulatory-CUSTOM: wl_cfg80211.c's wl_config_custom_regulatory()
sets WIPHY_FLAG_CUSTOM_REGULATORY / REGULATORY_CUSTOM_REG, so upstream 4.9
never applies the kernel's regdomain to it (wiphy->regulatory stays NULL, which
is why `iw reg get` prints "global"). The channel list and its flags come from
the wifi chip itself, read back through the WLC_GET_BANDLIST ioctl in
__wl_update_wiphybands().

The chip's MU country table omits UNII-3, so channels 144-165 render
"(disabled)" no matter what the kernel's regdb says. The only way to change
that is to programme the chip with a different country code.

The single entry point that programmes the chip is:

    wl_cfg80211_set_country_code()
        -> wl_is_ccode_change_required()   (skips if unchanged)
        -> wl_norm_cc_for_set()
        -> wldev_set_country(net, norm_cc)  (programmes the chip)

and it is reached from two places:
  * wl_cfgvendor.c  - the framework's netlink vendor event
                      (AOSP_COUNTRY_ATTRIBUTE / ANDR_WIFI_ATTRIBUTE_COUNTRY)
  * wl_android.c    - the "DRIVER COUNTRY <cc>" private command

The remap must happen BEFORE wl_is_ccode_change_required(), otherwise the
driver compares "MU" against its cached "MU", decides nothing changed, and
returns early without ever programming the chip. The framework's MU event is
delivered on every boot (the driver logs "country code = MU/0 is already
configured"), so with the remap in front of the check, the chip gets
programmed with the target country instead.

Target country: any that grants UNII-3 (149-165) in the Broadcom table.
"US" does; ZA / IN / AE / GB usually do as well. Change TARGET_COUNTRY and
rebuild if the first choice does not light up 149-165.

Regulatory note: the radio will then be operating under the target country's
rules for the affected channels. That is a regulatory decision, not a
technical one.
"""
import sys

PATH_DEFAULT = "drivers/net/wireless/bcmdhd_101_16/wl_cfg80211.c"
MARK = "PATCH-MU2US"
TARGET_COUNTRY = "US"

ANCHOR = "\tif ((wl_is_ccode_change_required(net, country_code, revinfo) == false) &&"

PATCH = (
    "\t/* " + MARK + ": remap MU -> " + TARGET_COUNTRY + " before the change check, so the\n"
    "\t * wifi chip is programmed with a country table that grants UNII-3 (149-165).\n"
    "\t */\n"
    "\tif (country_code && !strncmp(country_code, \"MU\", 2)) {\n"
    "\t\tcountry_code = \"" + TARGET_COUNTRY + "\";\n"
    "\t}\n"
)


def main(argv):
    path = argv[1] if len(argv) > 1 else PATH_DEFAULT
    try:
        src = open(path).read()
    except OSError as exc:
        print("FATAL: cannot read %s: %s" % (path, exc))
        return 1
    if MARK in src:
        print("already patched: %s" % path)
        return 0
    if ANCHOR not in src:
        print("FATAL: anchor not found in %s" % path)
        return 1
    open(path, "w").write(src.replace(ANCHOR, PATCH + ANCHOR, 1))
    print("patched %s (MU -> %s)" % (path, TARGET_COUNTRY))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
