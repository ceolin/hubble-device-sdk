/*
 * Copyright (c) 2026 Hubble Network, Inc.
 * SPDX-License-Identifier: Apache-2.0
 */
#include "app.h"

#include <hubble/hubble.h>
#include <hubble/ble.h>

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/logging/log.h>
#include <zephyr/zbus/zbus.h>

LOG_MODULE_REGISTER(ble);

#define HUBBLE_BLE_UUID_CONNECTABLE 0xFCA7
#define BLE_BUFFER_SIZE             31

#define APP_SVC_UUID                                                           \
	BT_UUID_128_ENCODE(0x9f7a2c4e, 0x3b61, 0x4d8a, 0xa2f5, 0x7c19e6b042d3)
#define APP_CHR_UUID                                                           \
	BT_UUID_128_ENCODE(0x9f7a2c4e, 0x3b61, 0x4d8a, 0xa2f5, 0x7c19e6b042d4)

static const struct bt_uuid_128 app_svc_uuid = BT_UUID_INIT_128(APP_SVC_UUID);
static const struct bt_uuid_128 app_chr_uuid = BT_UUID_INIT_128(APP_CHR_UUID);

static const struct bt_data app_sd[] = {
	BT_DATA(BT_DATA_NAME_COMPLETE, CONFIG_BT_DEVICE_NAME,
		sizeof(CONFIG_BT_DEVICE_NAME) - 1),
};

static uint8_t _master_key_count;
static uint8_t _master_key[CONFIG_HUBBLE_KEY_SIZE];
static uint8_t _adv_buffer[BLE_BUFFER_SIZE];
static uint64_t _epoch_time;
static struct bt_data app_ad[2] = {};

enum app_cmd {
	APP_BLE_PKT_ACK,
	APP_BLE_PKT_NACK,
	APP_BLE_PKT_CMD,
};

enum app_cmd_options {
	APP_BLE_CMD_KEY_SET,
	APP_BLE_CMD_EPOCH_SET,
	APP_BLE_CMD_ORBITAL_INFO_SET,
};

ZBUS_CHAN_DECLARE(app_data_chan);

static int _bt_init(void)
{
	if (!bt_is_ready()) {
		return bt_enable(NULL);
	}

	return 0;
}

static void _provision_cb(void)
{
	if (_bt_init() != 0) {
		LOG_ERR("Bluetooth failed to init");
		return;
	}

	app_ad[0] = (struct bt_data)BT_DATA_BYTES(
		BT_DATA_UUID16_ALL,
		BT_UUID_16_ENCODE(HUBBLE_BLE_UUID_CONNECTABLE));

	(void)bt_le_adv_start(
		BT_LE_ADV_PARAM(BT_LE_ADV_OPT_USE_NRPA | BT_LE_ADV_OPT_CONN,
				BT_GAP_ADV_FAST_INT_MIN_2,
				BT_GAP_ADV_FAST_INT_MAX_2, NULL),
		app_ad, 1, app_sd, ARRAY_SIZE(app_sd));
}

int _advertise_cb(void)
{
	int ret;
	size_t out_len = BLE_BUFFER_SIZE;

	ret = _bt_init();
	if (ret != 0) {
		LOG_ERR("Bluetooth failed to init");
		return ret;
	}

	ret = hubble_ble_advertise_get(NULL, 0, _adv_buffer, &out_len);
	if (ret != 0) {
		return ret;
	}

	app_ad[0] = (struct bt_data)BT_DATA_BYTES(
		BT_DATA_UUID16_ALL, BT_UUID_16_ENCODE(HUBBLE_BLE_UUID));
	app_ad[1].data_len = out_len;
	app_ad[1].type = BT_DATA_SVC_DATA16;
	app_ad[1].data = _adv_buffer;

	return bt_le_adv_start(BT_LE_ADV_PARAM(BT_LE_ADV_OPT_USE_NRPA,
					       BT_GAP_ADV_FAST_INT_MIN_2,
					       BT_GAP_ADV_FAST_INT_MAX_2, NULL),
			       app_ad, ARRAY_SIZE(app_ad), NULL, 0);
}

static void _stop_ble_cb(void)
{
	(void)bt_le_adv_stop();
	(void)bt_disable();
}

static void hubble_ble_cb(const struct zbus_channel *chan)
{
	const struct app_msg *msg = zbus_chan_const_msg(chan);

	switch (msg->type) {
	case PROVISION:
		_provision_cb();
		break;
	case ADVERTISE:
		_advertise_cb();
		break;
	case STOP_BLE:
		_stop_ble_cb();
	default:
		/* Just ignore other messages */
		break;
	}
}

ZBUS_LISTENER_DEFINE(ble_listener, hubble_ble_cb);


static void _connected_cb(struct bt_conn *conn, uint8_t err)
{
	ARG_UNUSED(conn);
	ARG_UNUSED(err);
}

static void _disconnected_cb(struct bt_conn *conn, uint8_t reason)
{
	int err = -EINVAL;

	ARG_UNUSED(conn);
	ARG_UNUSED(reason);

	if ((_epoch_time != 0) && (_master_key_count == CONFIG_HUBBLE_KEY_SIZE)) {
		err = hubble_init(_epoch_time, _master_key);
	}

	printk("RA\n");

	if (err == 0) {
		zbus_chan_pub(&app_data_chan,
			      &(struct app_msg){.type = ADVERTISE}, K_FOREVER);
	} else {
		zbus_chan_pub(&app_data_chan,
			      &(struct app_msg){.type = PROVISION}, K_FOREVER);
	}
	zbus_chan_pub(&app_data_chan,
		      &(struct app_msg){.type = TRANSMIT_SAT}, K_FOREVER);
}

BT_CONN_CB_DEFINE(conn_callbacks) = {
	.connected = _connected_cb,
	.disconnected = _disconnected_cb,
};

static ssize_t _app_chr_write_cb(
	struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *data,
	uint16_t len, uint16_t offset, uint8_t flags)
{
	int ret = -EINVAL;

	if (((uint8_t *)data)[0] != APP_BLE_PKT_CMD) {
		return -ENOENT;
	}

	switch (((uint8_t *)data)[1]) {
	case APP_BLE_CMD_ORBITAL_INFO_SET:
		/* TODO */
		break;
	case APP_BLE_CMD_KEY_SET:
		if ((len > 2U) && (_master_key_count <= CONFIG_HUBBLE_KEY_SIZE)) {
			memcpy(_master_key + _master_key_count,
			       (uint8_t *)data + 2, len - 2);
			_master_key_count += len - 2;
			ret = len;
		}
		break;
	case APP_BLE_CMD_EPOCH_SET:
		if (len != (2 + sizeof(uint64_t))) {
			break;
		}
		memcpy(&_epoch_time, (uint8_t *)data + 2, sizeof(_epoch_time));
		_epoch_time = _epoch_time - k_uptime_get();
		ret = len;
		break;
	default:
		break;
	}

	return ret;
}

BT_GATT_SERVICE_DEFINE(
	vnd_svc, BT_GATT_PRIMARY_SERVICE(&app_svc_uuid),
	BT_GATT_CHARACTERISTIC(
		&app_chr_uuid.uuid,
		BT_GATT_CHRC_WRITE | BT_GATT_CHRC_WRITE_WITHOUT_RESP,
		BT_GATT_PERM_WRITE, NULL, _app_chr_write_cb, NULL), );
