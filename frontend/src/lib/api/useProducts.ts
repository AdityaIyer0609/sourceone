import { listProducts } from './products'
import { useApiQuery } from './useApiQuery'

export function useProducts() {
  return useApiQuery('products', (signal) => listProducts({}, signal))
}
