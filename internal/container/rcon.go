package container

import (
	"bytes"
	"encoding/binary"
	"fmt"
	"net"
	"sync"
	"sync/atomic"
)

type RCON struct {
	mu       sync.Mutex
	addr     string
	password string
	conn     net.Conn
	id       int32
}

func NewRCON(addr, password string) *RCON {
	return &RCON{addr: addr, password: password}
}

func (r *RCON) connect() error {
	if r.conn != nil {
		return nil
	}
	conn, err := net.Dial("tcp", r.addr)
	if err != nil {
		return fmt.Errorf("rcon connect: %w", err)
	}
	r.conn = conn
	r.id = 1
	return r.authenticate()
}

func (r *RCON) disconnect() {
	if r.conn != nil {
		r.conn.Close()
		r.conn = nil
	}
}

func (r *RCON) authenticate() error {
	id := atomic.AddInt32(&r.id, 1)
	return r.sendPacket(id, 3, r.password)
}

func (r *RCON) Command(cmd string) (string, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	if r.conn == nil {
		if err := r.connect(); err != nil {
			return "", err
		}
	}

	id := atomic.AddInt32(&r.id, 1)
	if err := r.sendPacket(id, 2, cmd); err != nil {
		r.disconnect()
		return "", fmt.Errorf("rcon send: %w", err)
	}

	resp, err := r.receive(id)
	if err != nil {
		r.disconnect()
		return "", fmt.Errorf("rcon recv: %w", err)
	}
	return resp, nil
}

func (r *RCON) sendPacket(id int32, pktType int32, payload string) error {
	p := append([]byte(payload), 0, 0)
	length := int32(len(p) + 4 + 4)

	buf := new(bytes.Buffer)
	binary.Write(buf, binary.LittleEndian, length)
	binary.Write(buf, binary.LittleEndian, id)
	binary.Write(buf, binary.LittleEndian, pktType)
	buf.Write(p)

	_, err := r.conn.Write(buf.Bytes())
	return err
}

func (r *RCON) receive(expectedID int32) (string, error) {
	var length int32
	if err := binary.Read(r.conn, binary.LittleEndian, &length); err != nil {
		return "", err
	}
	if length < 8 {
		return "", fmt.Errorf("rcon packet too short: %d", length)
	}

	buf := make([]byte, length)
	if _, err := r.conn.Read(buf); err != nil {
		return "", err
	}

	id := int32(binary.LittleEndian.Uint32(buf[0:4]))
	if id == -1 {
		return "", fmt.Errorf("rcon auth failed")
	}

	payload := string(buf[8 : len(buf)-2])
	return payload, nil
}
