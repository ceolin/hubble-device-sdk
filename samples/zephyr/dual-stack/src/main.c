/*
 * Copyright (c) 2026 Hubble Network, Inc.
 * SPDX-License-Identifier: Apache-2.0
 */

#include "app.h"

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/zbus/zbus.h>

#include <stdint.h>
#include <stdlib.h>
#include <string.h>


LOG_MODULE_REGISTER(main);

ZBUS_CHAN_DEFINE(app_data_chan,
		 struct app_msg,

		 NULL, /* Validator */
		 NULL, /* User data */
		 ZBUS_OBSERVERS(sat_subscriber, ble_listener),
		 ZBUS_MSG_INIT(0)
 );


int main(void)
{
	LOG_INF("Hubble Network Dual stack Sample started");

	/* Kicking provisioning */
	zbus_chan_pub(&app_data_chan, &(struct app_msg){.type = PROVISION}, K_FOREVER);

	return 0;
}
