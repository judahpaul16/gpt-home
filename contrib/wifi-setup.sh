#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [ "$(id -u)" -ne 0 ]; then
    echo -e "${RED}This script must be run as root.${NC}"
    exit 1
fi

IFACE="${WIFI_IFACE:-wlan0}"
COUNTRY="${WIFI_COUNTRY:-US}"

if [ -n "${WIFI_SSID:-}" ] && [ -n "${WIFI_PSK:-}" ]; then
    SSID="$WIFI_SSID"
    PSK="$WIFI_PSK"
else
    read -rp "SSID: " SSID
    read -rsp "Password: " PSK
    echo
fi

if [ -z "$SSID" ]; then
    echo -e "${RED}SSID cannot be empty.${NC}"
    exit 1
fi

echo -e "${GREEN}Configuring Wi-Fi for '${SSID}' on ${IFACE}...${NC}"

echo -e "${YELLOW}Stopping and disabling NetworkManager...${NC}"
systemctl stop NetworkManager 2>/dev/null || true
systemctl disable NetworkManager 2>/dev/null || true
systemctl mask NetworkManager 2>/dev/null || true

systemctl stop ModemManager 2>/dev/null || true
systemctl disable ModemManager 2>/dev/null || true

systemctl stop wpa_supplicant.service 2>/dev/null || true
systemctl disable wpa_supplicant.service 2>/dev/null || true

echo -e "${YELLOW}Configuring wpa_supplicant...${NC}"
WPA_CONF="/etc/wpa_supplicant/wpa_supplicant-${IFACE}.conf"
mkdir -p /etc/wpa_supplicant

cat > "$WPA_CONF" <<EOF
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=${COUNTRY}

EOF

wpa_passphrase "$SSID" "$PSK" | grep -v '#psk' >> "$WPA_CONF"
chmod 600 "$WPA_CONF"

echo -e "${YELLOW}Configuring systemd-networkd (${IFACE})...${NC}"
mkdir -p /etc/systemd/network

cat > "/etc/systemd/network/25-${IFACE}.network" <<EOF
[Match]
Name=${IFACE}

[Network]
DHCP=yes
DNS=1.1.1.1
DNS=8.8.8.8

[DHCP]
UseDNS=false
RouteMetric=600
EOF

echo -e "${YELLOW}Configuring DNS resolvers...${NC}"
chattr -i /etc/resolv.conf 2>/dev/null || true
rm -f /etc/resolv.conf
cat > /etc/resolv.conf <<EOF
nameserver 1.1.1.1
nameserver 8.8.8.8
EOF
chattr +i /etc/resolv.conf

echo -e "${YELLOW}Disabling Wi-Fi power save...${NC}"
cat > /etc/systemd/system/wifi-powersave-off.service <<EOF
[Unit]
Description=Disable Wi-Fi power save
After=sys-subsystem-net-devices-${IFACE}.device
Wants=sys-subsystem-net-devices-${IFACE}.device

[Service]
Type=oneshot
ExecStart=/sbin/iw dev ${IFACE} set power_save off
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable wifi-powersave-off.service

echo -e "${YELLOW}Setting Wi-Fi regulatory domain...${NC}"
iw reg set "$COUNTRY" 2>/dev/null || true
if [ -f /etc/default/crda ]; then
    sed -i "s/^REGDOMAIN=.*/REGDOMAIN=${COUNTRY}/" /etc/default/crda
else
    echo "REGDOMAIN=${COUNTRY}" > /etc/default/crda
fi

echo -e "${YELLOW}Enabling services...${NC}"
systemctl enable systemd-networkd
systemctl enable "wpa_supplicant@${IFACE}"

echo -e "${YELLOW}Starting services...${NC}"
rfkill unblock wifi 2>/dev/null || true
ip link set "$IFACE" up
sleep 1
systemctl restart systemd-networkd
systemctl restart "wpa_supplicant@${IFACE}"
sleep 2
systemctl start wifi-powersave-off.service 2>/dev/null || true

echo -e "${YELLOW}Waiting for connection...${NC}"
for i in $(seq 1 15); do
    if ip addr show "$IFACE" | grep -q "inet "; then
        IP=$(ip -4 addr show "$IFACE" | grep -oP '(?<=inet\s)\d+(\.\d+){3}')
        echo -e "${GREEN}Connected! IP: ${IP}${NC}"
        echo -e "${GREEN}DNS: $(grep nameserver /etc/resolv.conf | head -2)${NC}"
        exit 0
    fi
    sleep 1
done

echo -e "${RED}Failed to obtain IP address within 15 seconds.${NC}"
echo "Check: journalctl -u wpa_supplicant@${IFACE} -u systemd-networkd --no-pager -n 20"
exit 1
