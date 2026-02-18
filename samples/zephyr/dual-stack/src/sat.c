/*
 * Copyright (c) 2026 HubbleNetwork
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#include "app.h"

#include <zephyr/logging/log.h>
#include <zephyr/zbus/zbus.h>

#define APP_MSG_MAX 4

LOG_MODULE_REGISTER(sat);

ZBUS_SUBSCRIBER_DEFINE(sat_subscriber, APP_MSG_MAX);

static void sat_thread(void *arg1, void *arg2, void *arg3)
{
	const struct zbus_channel *chan;

	while (!zbus_sub_wait(&sat_subscriber, &chan, K_FOREVER)) {
		struct app_msg msg;

		zbus_chan_read(chan, &msg, K_MSEC(200));

		switch (msg.type) {
		case SCHEDULE_SAT_TRANSMISSION:
			printk("SCHEDULE_SAT_TRANSMISSION\n");
			break;
		case TRANSMIT_SAT:
			printk("TRANSMIT_SAT\n");
			break;
		default:
			break;
		}
	}
}

K_THREAD_DEFINE(sat_thread_id, CONFIG_MAIN_STACK_SIZE, sat_thread, NULL, NULL, NULL, 5, 0, 0);
