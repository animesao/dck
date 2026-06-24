//go:build !linux

package cmd

func readDiskUsage(path string) (total, used uint64, pct float64) {
	return 0, 0, 0
}
