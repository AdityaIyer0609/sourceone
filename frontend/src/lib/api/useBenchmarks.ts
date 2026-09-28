import { listBenchmarks } from './pricing'
import { useApiQuery } from './useApiQuery'

export function useBenchmarks() {
  return useApiQuery('benchmarks', (signal) => listBenchmarks({}, signal))
}
