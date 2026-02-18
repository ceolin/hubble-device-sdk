/*
 * Copyright (c) 2026 HubbleNetwork
 *
 * SPDX-License-Identifier: Apache-2.0
 */
#ifndef _APP_H_
#define _APP_H_

enum msg_type {
	PROVISION,
	ADVERTISE,
	STOP_BLE,
	SCHEDULE_SAT_TRANSMISSION,
	TRANSMIT_SAT,
};

struct app_msg {
	enum msg_type type;
};

int app_ble_init(void);

#endif /* _APP_H_ */
