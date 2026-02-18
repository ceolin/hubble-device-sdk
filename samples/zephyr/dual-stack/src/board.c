/*
 * Copyright (c) 2026 Hubble Network, Inc.
 * SPDX-License-Identifier: Apache-2.0
 */

#include <hubble/hubble.h>
#include <hubble/sat/packet.h>

#include <zephyr/kernel.h>

int hubble_sat_board_init(void)
{
	return 0;
}

int hubble_sat_board_enable(void)
{
	return 0;
}

int hubble_sat_board_disable(void)
{
	return 0;
}

int hubble_sat_board_packet_send(const struct hubble_sat_packet *packet)
{
	ARG_UNUSED(packet);

	return 0;
}
