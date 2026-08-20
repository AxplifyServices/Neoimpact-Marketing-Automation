import { useState, useEffect, ReactNode } from 'react'
import {
  flexRender,
  getCoreRowModel,
  getFacetedRowModel,
  getFacetedUniqueValues,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type ColumnFiltersState,
  type SortingState,
  type VisibilityState,
  type RowSelectionState,
  type Table as TableType,
} from '@tanstack/react-table'
import { DataTableSkeleton } from './skeleton'
import { useIsMobile } from '@/hooks/use-mobile'

interface PaginationCallbacks {
  onPageChange?: (page: number) => void
  onPageSizeChange?: (pageSize: number) => void
  sorting?: SortingState
  onSortingChange?: (sorting: SortingState) => void
}

interface DataTableProps<TData, TValue> {
  columns: ColumnDef<TData, TValue>[]
  data: TData[]
  isLoading?: boolean
  isError?: boolean
  error?: Error | null
  pagination?: {
    currentPage: number
    totalPages: number
    pageSize: number
  }
  onPageChange?: (page: number) => void
  onPageSizeChange?: (pageSize: number) => void
  sorting?: SortingState
  onSortingChange?: (sorting: SortingState) => void
  toolbar?: (table: TableType<TData>) => ReactNode
  bulkActions?: (table: TableType<TData>) => ReactNode
  paginationComponent?: (table: TableType<TData>, callbacks?: PaginationCallbacks) => ReactNode
}

export function DataTable<TData, TValue>({
  columns,
  data,
  isLoading = false,
  isError = false,
  error,
  pagination,
  onPageChange,
  onPageSizeChange,
  sorting: controlledSorting,
  onSortingChange: controlledSortingChange,
  toolbar,
  bulkActions,
  paginationComponent,
}: DataTableProps<TData, TValue>) {
  const [sorting, setSorting] = useState<SortingState>([])
  const effectiveSorting = controlledSorting ?? sorting
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([])

  // Initialize column visibility with default hidden columns
  const getInitialColumnVisibility = () => {
    const initialVisibility: VisibilityState = {}
    columns.forEach((column) => {
      if ((column.meta as any)?.defaultHidden) {
        const key = ('accessorKey' in column ? column.accessorKey : column.id) as string | undefined
        if (key) initialVisibility[key] = false
      }
    })
    return initialVisibility
  }

  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>(getInitialColumnVisibility())
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({})
  const [globalFilter, setGlobalFilter] = useState('')
  const [paginationState, setPaginationState] = useState({ pageIndex: 0, pageSize: 10 })
  const isManualPagination = !!pagination
  const isMobile = useIsMobile()

  // Clear row selection when page changes
  useEffect(() => {
    setRowSelection({})
  }, [pagination?.currentPage, paginationState.pageIndex])

  const table = useReactTable({
    data,
    columns,
    pageCount: pagination ? pagination.totalPages : undefined,
    state: {
      sorting: effectiveSorting,
      columnFilters,
      columnVisibility,
      rowSelection,
      globalFilter,
      pagination: pagination
        ? {
            pageIndex: pagination.currentPage ?? 0,
            pageSize: pagination.pageSize ?? 10,
          }
        : paginationState,
    },
    manualPagination: isManualPagination,
    enableRowSelection: true,
    onPaginationChange: isManualPagination ? undefined : setPaginationState,
    onRowSelectionChange: setRowSelection,
    manualSorting: !!controlledSortingChange,
    onSortingChange: (updater) => {
      const next = typeof updater === 'function' ? updater(effectiveSorting) : updater
      if (controlledSortingChange) controlledSortingChange(next)
      else setSorting(next)
    },
    onColumnFiltersChange: setColumnFilters,
    onColumnVisibilityChange: setColumnVisibility,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFacetedRowModel: getFacetedRowModel(),
    getFacetedUniqueValues: getFacetedUniqueValues(),
  })

  return (
    <div className='space-y-4'>
      {toolbar && toolbar(table)}

      {/* Desktop/Tablet: mount only one representation to halve DOM/render work. */}
      {!isMobile && (
      <div className='rounded-md border overflow-hidden'>
        <div className='overflow-x-auto'>
          <table className='w-full'>
            <thead className='bg-white'>
              {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id} className='border-b'>
                  {headerGroup.headers.map((header) => (
                    <th
                      key={header.id}
                      className='h-10 px-3 text-left align-middle font-medium text-muted-foreground'
                    >
                      {header.isPlaceholder
                        ? null
                        : flexRender(header.column.columnDef.header, header.getContext())}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {isError ? (
                <tr>
                  <td colSpan={columns.length} className='h-24 text-center'>
                    <div className='flex flex-col items-center gap-2'>
                      <p className='text-destructive font-medium'>Error loading data</p>
                      <p className='text-sm text-muted-foreground'>{error?.message || 'An error occurred'}</p>
                    </div>
                  </td>
                </tr>
              ) : isLoading ? (
                <DataTableSkeleton columnCount={columns.length} rowCount={pagination?.pageSize ?? 10} />
              ) : table.getRowModel().rows?.length ? (
                table.getRowModel().rows.map((row) => (
                  <tr
                    key={row.id}
                    className='bg-white border-b transition-colors hover:bg-gray-50 data-[state=selected]:bg-blue-50'
                    data-state={row.getIsSelected() ? 'selected' : undefined}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className='p-3 align-middle'>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={columns.length} className='h-24 text-center'>
                    No results.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
      )}

      {/* Mobile: cards only; the desktop table is not mounted in parallel. */}
      {isMobile && (
      <div className='space-y-4'>
        {isError ? (
          <div className='rounded-md border p-8'>
            <div className='flex flex-col items-center gap-2'>
              <p className='text-destructive font-medium'>Error loading data</p>
              <p className='text-sm text-muted-foreground'>{error?.message || 'An error occurred'}</p>
            </div>
          </div>
        ) : isLoading ? (
          <div className='space-y-4'>
            {Array.from({ length: pagination?.pageSize ?? 10 }).map((_, i) => (
              <div key={i} className='rounded-md border p-4 space-y-3'>
                <div className='h-6 bg-white rounded animate-pulse' />
                <div className='h-4 bg-white rounded animate-pulse w-3/4' />
                <div className='h-4 bg-white rounded animate-pulse w-1/2' />
              </div>
            ))}
          </div>
        ) : table.getRowModel().rows?.length ? (
          table.getRowModel().rows.map((row) => (
            <div
              key={row.id}
              className='rounded-md border bg-white p-4 space-y-3'
              data-state={row.getIsSelected() ? 'selected' : undefined}
            >
              {row.getVisibleCells().map((cell) => {
                const header = cell.column.columnDef.header
                const headerText = typeof header === 'string' ? header : ''
                return (
                  <div key={cell.id} className='flex flex-col gap-1'>
                    {headerText && (
                      <span className='text-xs font-medium text-muted-foreground'>
                        {headerText}
                      </span>
                    )}
                    <div className='text-sm'>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </div>
                  </div>
                )
              })}
            </div>
          ))
        ) : (
          <div className='rounded-md border p-8 text-center'>
            No results.
          </div>
        )}
      </div>
      )}

      {paginationComponent && paginationComponent(table, { onPageChange, onPageSizeChange })}

      {bulkActions && bulkActions(table)}
    </div>
  )
}
