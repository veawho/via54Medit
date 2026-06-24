package source

import "encoding/json"

// jsonDecoder is a tiny indirection so test code can wrap a ResponseRecorder
// body. Phase 1 only: we use stdlib json.NewDecoder directly.
func jsonDecoder(r interface{ Read(p []byte) (int, error) }, v any) error {
	return json.NewDecoder(r).Decode(v)
}
