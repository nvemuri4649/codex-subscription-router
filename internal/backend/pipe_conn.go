package backend

import (
	"io"
	"net"
	"sync"
	"time"
)

// PipeConn carries a WebSocket handshake and frames over an SSH stdio stream.
// It never binds a network port. Closing it closes only the transport, not the
// persistent remote app server behind it.
type PipeConn struct {
	Reader  io.ReadCloser
	Writer  io.WriteCloser
	OnClose func()
	once    sync.Once
}

func (c *PipeConn) Read(p []byte) (int, error)  { return c.Reader.Read(p) }
func (c *PipeConn) Write(p []byte) (int, error) { return c.Writer.Write(p) }
func (c *PipeConn) Close() error {
	c.once.Do(func() {
		_ = c.Reader.Close()
		_ = c.Writer.Close()
		if c.OnClose != nil {
			c.OnClose()
		}
	})
	return nil
}
func (*PipeConn) LocalAddr() net.Addr  { return pipeAddr("stdio") }
func (*PipeConn) RemoteAddr() net.Addr { return pipeAddr("ssh") }
func (c *PipeConn) SetDeadline(t time.Time) error {
	_ = c.SetReadDeadline(t)
	return c.SetWriteDeadline(t)
}
func (c *PipeConn) SetReadDeadline(t time.Time) error {
	if d, ok := c.Reader.(interface{ SetReadDeadline(time.Time) error }); ok {
		return d.SetReadDeadline(t)
	}
	return nil
}
func (c *PipeConn) SetWriteDeadline(t time.Time) error {
	if d, ok := c.Writer.(interface{ SetWriteDeadline(time.Time) error }); ok {
		return d.SetWriteDeadline(t)
	}
	return nil
}

type pipeAddr string

func (a pipeAddr) Network() string { return "stdio" }
func (a pipeAddr) String() string  { return string(a) }
