import { useQuery } from '@tanstack/react-query';
import { dataApi } from '@/lib/api/definitions/data.api';
import { getApiClient } from '@/lib/api/api-client';

interface TablesResponse {
  tables: string[];
}

interface ColumnsResponse {
  table: string;
  columns: {
    name: string;
    type: string;
  }[];
}

export function useHistoriqueData() {
  const apiClient = getApiClient();

  // Fetch available tables
  const { data: tablesResponse, isLoading: tablesLoading } = useQuery<TablesResponse>({
    queryKey: ['data-tables'],
    queryFn: () => apiClient.request<TablesResponse>(dataApi.getTables()),
  });

  // Convert string array to objects with name property
  const tables = (tablesResponse?.tables || []).map(name => ({ name, display_name: name }));

  return {
    tables,
    isLoading: tablesLoading,
  };
}

export function useTableColumns(tableName: string | null) {
  const apiClient = getApiClient();

  const { data: columnsResponse, isLoading } = useQuery<ColumnsResponse>({
    queryKey: ['table-columns', tableName],
    queryFn: () => apiClient.request<ColumnsResponse>(dataApi.getTableColumns(tableName!)),
    enabled: !!tableName,
  });

  const columns = columnsResponse?.columns || [];

  return {
    columns,
    isLoading,
  };
}

export function useDistinctValues(tableName: string | null, columnName: string | null) {
  const apiClient = getApiClient();

  const { data: values = [], isLoading } = useQuery<string[]>({
    queryKey: ['distinct-values', tableName, columnName],
    queryFn: () => apiClient.request<string[]>(dataApi.getDistinctValues(tableName!, columnName!)),
    enabled: !!tableName && !!columnName,
  });

  return {
    values,
    isLoading,
  };
}

export type TableFilterKind = 'numeric' | 'categorical' | 'text';
export interface TableFilterOptionMeta {
  kind: TableFilterKind;
  options?: string[];
}

interface FilterOptionsResponse {
  table: string;
  filters: Record<string, TableFilterOptionMeta>;
}

export function useTableFilterOptions(tableName: string | null, columnNames: string[]) {
  const apiClient = getApiClient();
  const stableColumns = columnNames.join('|');
  const { data, isLoading } = useQuery<FilterOptionsResponse>({
    queryKey: ['table-filter-options', tableName, stableColumns],
    queryFn: () => apiClient.request<FilterOptionsResponse>(dataApi.getFilterOptions(tableName!, columnNames)),
    enabled: !!tableName && columnNames.length > 0,
    staleTime: 5 * 60_000,
  });
  return { filterOptions: data?.filters ?? {}, isLoading };
}
