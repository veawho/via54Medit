package source

import "encoding/xml"

// xmlDecode is a thin indirection for tests to mock (Phase 1: stdlib).
func xmlDecode(r interface{ Read(p []byte) (int, error) }, v any) error {
	return xml.NewDecoder(r).Decode(v)
}
