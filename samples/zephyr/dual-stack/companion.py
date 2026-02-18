#!/usr/bin/env python3
#
# Copyright (c) 2025 Hubble Network, Inc.
#
# SPDX-License-Identifier: Apache-2.0
import asyncio
import base64
import click
import datetime
import secrets
import struct
import time

from functools import partial
from types import SimpleNamespace
from typing import Optional, List

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from Crypto.Cipher import AES
from Crypto.Hash import CMAC
from Crypto.Protocol.KDF import SP800_108_Counter


HUBBLE_AES_NONCE_SIZE = 12
HUBBLE_AES_TAG_SIZE = 4

DUAL_STACK_SERVICE_UUID        = "9f7a2c4e-3b61-4d8a-a2f5-7c19e6b042d3"
DUAL_STACK_CHARACTERISTIC_UUID = "9f7a2c4e-3b61-4d8a-a2f5-7c19e6b042d4"

# Valid values are 16 and 32, respectively for AES-128 and AES-256
hubble_aes_key_size = 32

def key_validate(ctx: click.core.Context, param: click.core.Option, value: str) -> str:
    global hubble_aes_key_size

    # No key provided, just provide a random key for local test
    if value == None:
        return secrets.token_bytes(hubble_aes_key_size)

    size = len(value)
    if size != 24 and size != 44:
        raise click.BadParameter("Key must be 24/44 characters long (base64-encoded 16 bytes)")

    if size == 24:
        hubble_aes_key_size = 16

    return bytearray(base64.b64decode(value))

def auth_tag_check(payload: bytes, auth_tag: bytes, key: bytes, nonce: bytes) -> bool:
    cipher = AES.new(key, AES.MODE_CBC, mac_len=4, nonce=nonce)

    try:
        val = cipher.decrypt_and_verify(payload, auth_tag)
        return True
    except ValueError:
        return False

def generate_kdf_key(key: bytes, key_size: int, label: str, context: int) -> bytes:
    label = label.encode()
    context = str(context).encode()

    return SP800_108_Counter(
        key,
        key_size,
        lambda session_key, data: CMAC.new(session_key, data, AES).digest(),
        label=label,
        context=context,
    )

def get_nonce(master_key: bytes, time_counter: int, counter: int) -> bytes:
    nonce_key = generate_kdf_key(
        master_key, hubble_aes_key_size, "NonceKey", time_counter
    )

    return generate_kdf_key(nonce_key, HUBBLE_AES_NONCE_SIZE, "Nonce", counter)

def get_encryption_key(master_key: bytes, time_counter: int, counter: int) -> bytes:
    encryption_key = generate_kdf_key(
        master_key, hubble_aes_key_size, "EncryptionKey", time_counter
    )

    return generate_kdf_key(encryption_key, hubble_aes_key_size, 'Key', counter)

def get_auth_tag(key: bytes, ciphertext: bytes) -> bytes:
    computed_cmac = CMAC.new(key, ciphertext, AES).digest()

    return computed_cmac[:HUBBLE_AES_TAG_SIZE]


def aes_decrypt(key: bytes, session_nonce: bytes, ciphertext: bytes) -> bytes:
    cipher = AES.new(key, AES.MODE_CTR, nonce=session_nonce)

    return cipher.decrypt(ciphertext)


def parse_beacon_adv(master_key: bytes, ble_adv: bytes, days_offeset: int) -> SimpleNamespace:
    seq_no = int.from_bytes(ble_adv[0:2], "big") & 0x3FF
    device_id = ble_adv[2:6].hex()
    auth_tag = ble_adv[6:10]
    encrypted_payload = ble_adv[10:]
    day_offset = 0

    time_counter = int(datetime.datetime.now(datetime.UTC).timestamp()) // 86400

    for t in range(-day_offset, day_offset + 1):
        key = get_encryption_key(master_key, time_counter + t, seq_no)
        tag = get_auth_tag(key, encrypted_payload)
        if tag == auth_tag:
            day_offset = t
            nonce = get_nonce(master_key, time_counter + t, seq_no)
            decrypted_payload = aes_decrypt(key, nonce, encrypted_payload)

            return SimpleNamespace(device=device_id, counter=seq_no, payload=decrypted_payload, day_offset=day_offset)

    return None

async def provision_device(device: BLEDevice, key: bytes) -> None:
    try:
        async with BleakClient(device) as client:
            await client.connect()

            click.echo(f"Provisioning time {device}")
            data = bytearray([0x02, 0x01])
            data +=  bytearray(int(datetime.datetime.now(datetime.UTC).timestamp() * 1000).to_bytes(8, byteorder="little", signed=False))
            await client.write_gatt_char(DUAL_STACK_CHARACTERISTIC_UUID, data, response=True)

            click.echo(f"Provisioning key {device}")
            for chunk in [key[i:i+4] for i in range(0, len(key), 4)]:
                data = bytearray([0x02, 0x00])
                data += chunk
                await client.write_gatt_char(DUAL_STACK_CHARACTERISTIC_UUID, data, response=True)

            await client.disconnect()
    except asyncio.CancelledError:
        pass
    finally:
        return

def detection_callback(device: BLEDevice, advertisement_data: AdvertisementData,
                       key: bytes,) -> None:
    service_uuids = advertisement_data.service_uuids or []

    # Check if our target service UUID is in the advertisement
    for uuid in service_uuids:
        if "fca6" in uuid:
            data = parse_beacon_adv(key, advertisement_data.service_data[uuid], 2)
            if data is not None:
                click.echo(f"{'='*60}")
                click.echo(f"{data.device} : {device.address}")
                click.echo(f"counter: {data.counter} payload(bytes): {data.payload.hex()}")
                if data.day_offset != 0:
                    click.echo(f"THIS DEVICE IS OUT OF SYNC: {data.day_offset} days")
                click.echo(f"{'='*60}")
        elif "fca7" in uuid:
            try:
                asyncio.create_task(provision_device(device, key))
            except asyncio.CancelledError:
                pass


async def scan(key: bytes) -> None:
    click.echo(f"Scanning for Hubble BLE devices")
    click.echo("Press Ctrl+C to stop scanning...\n")

    scanner = BleakScanner(detection_callback=lambda d,
                           ad: detection_callback(d, ad, key=key))
    try:
        await scanner.start()
        # Keep scanning until interrupted
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        await scanner.stop()
        click.echo("\nScanning stopped.")


@click.command()
@click.option(
    "--key",
    "-k",
    type=str,
    envvar="HUBBLE_CRYPTO_KEY",
    default=None,
    show_default=False,
    callback = key_validate,
    help="Device crypto key (if not using HUBBLE_CRYPTO_KEY env var)",
)
def cli(key: str) -> None:
    try:
        asyncio.run(scan(key))
    except KeyboardInterrupt:
        click.echo("\nExiting...")

def main(argv: Optional[list[str]] = None) -> int:
    cli.main(args=argv, prog_name="Dual Stack companion", standalone_mode=True)

if __name__ == "__main__":
    main()
