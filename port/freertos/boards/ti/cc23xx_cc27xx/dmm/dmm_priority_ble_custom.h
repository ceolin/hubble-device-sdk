/*
 * Copyright (c) 2026 Hubble Network, Inc.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef DMM_PRIORITY_BLE_CUSTOM_H
#define DMM_PRIORITY_BLE_CUSTOM_H

#ifdef __cplusplus
extern "C" {
#endif

#include "dmm_policy.h"

/* Number of activities */
#define ACTIVITY_NUM_BLE    6
#define ACTIVITY_NUM_CUSTOM 6

extern GlobalTable globalPriorityTable_bleCustom[DMMPOLICY_NUM_STACKS];

#ifdef __cplusplus
}
#endif

#endif /* DMM_PRIORITY_BLE_CUSTOM_H */
