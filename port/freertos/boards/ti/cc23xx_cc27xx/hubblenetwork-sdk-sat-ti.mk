# Copyright (c) 2026 Hubble Network, Inc.
#
# SPDX-License-Identifier: Apache-2.0

THIS_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

HUBBLENETWORK_SDK_FLAGS += \
	-I$(THIS_DIR)/dmm \
	-I$(THIS_DIR)/../ \
	-I$(THIS_DIR)/../../../

HUBBLENETWORK_SDK_SOURCES += \
	$(THIS_DIR)/radio.c

ifneq (,$(findstring -DUSE_DMM,$(CFLAGS)))
HUBBLENETWORK_SDK_SOURCES += \
	$(THIS_DIR)/dmm/dmm_priority_ble_custom.c \
	$(THIS_DIR)/dmm/rcl_override_dmm.c \
	$(THIS_DIR)/radio_config/ti_radio_config_cc23_dmm.c
else
HUBBLENETWORK_SDK_SOURCES += \
	$(THIS_DIR)/radio_config/ti_radio_config_cc23.c
endif
