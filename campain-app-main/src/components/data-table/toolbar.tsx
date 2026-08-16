import { useState, useEffect, useRef } from 'react'
import { Cross2Icon } from '@radix-ui/react-icons'
import { type Table } from '@tanstack/react-table'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { DataTableFacetedFilter } from './faceted-filter'
import { DataTableViewOptions } from './view-options'

type DataTableToolbarProps<TData> = {
  table: Table<TData>
  searchPlaceholder?: string
  searchKey?: string
  filters?: {
    columnId: string
    title: string
    options: {
      label: string
      value: string
      icon?: React.ComponentType<{ className?: string }>
    }[]
  }[]
  /** Custom action buttons to render on the right (e.g., "New" button) */
  actions?: React.ReactNode
  /** Server-side search callback - triggers debounced search after 500ms */
  onSearchChange?: (search: string) => void
  /** Controlled search value for server-side search */
  searchValue?: string
  /** Additional filter components to render (e.g., Advanced Filters) */
  children?: React.ReactNode
  /** Callback when reset button is clicked */
  onReset?: () => void
}

export function DataTableToolbar<TData>({
  table,
  searchPlaceholder = 'Filter...',
  searchKey,
  filters = [],
  actions,
  onSearchChange,
  searchValue,
  children,
  onReset,
}: DataTableToolbarProps<TData>) {
  const [localSearch, setLocalSearch] = useState(searchValue ?? '')
  const isFirstRender = useRef(true)
  const isServerSideSearch = !!onSearchChange

  // Debounce search for server-side mode
  useEffect(() => {
    if (!isServerSideSearch) return

    if (isFirstRender.current) {
      isFirstRender.current = false
      return
    }

    const timer = setTimeout(() => {
      onSearchChange(localSearch)
    }, 500)

    return () => clearTimeout(timer)
  }, [localSearch, onSearchChange, isServerSideSearch])

  // Sync with external search value changes (server-side mode)
  useEffect(() => {
    if (isServerSideSearch && searchValue !== undefined) {
      setLocalSearch(searchValue)
    }
  }, [searchValue, isServerSideSearch])

  const isFiltered =
    table.getState().columnFilters.length > 0 ||
    table.getState().globalFilter ||
    (isServerSideSearch && localSearch)

  const handleReset = () => {
    table.resetColumnFilters()
    table.setGlobalFilter('')
    if (isServerSideSearch) {
      setLocalSearch('')
    }
    if (onReset) {
      onReset()
    }
  }

  return (
    <div className='flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between'>
      {/* Left side: Search and filters */}
      <div className='flex flex-1 flex-wrap items-center gap-2'>
        {/* Search input */}
        <div className='w-full sm:w-auto'>
          {isServerSideSearch ? (
            <Input
              placeholder={searchPlaceholder}
              value={localSearch}
              onChange={(event) => setLocalSearch(event.target.value)}
              className='h-8 w-full sm:w-[200px] lg:w-[250px]'
              aria-label={searchPlaceholder}
              type='search'
            />
          ) : searchKey ? (
            <Input
              placeholder={searchPlaceholder}
              value={
                (table.getColumn(searchKey)?.getFilterValue() as string) ?? ''
              }
              onChange={(event) =>
                table.getColumn(searchKey)?.setFilterValue(event.target.value)
              }
              className='h-8 w-full sm:w-[200px] lg:w-[250px]'
              aria-label={searchPlaceholder}
              type='search'
            />
          ) : (
            <Input
              placeholder={searchPlaceholder}
              value={table.getState().globalFilter ?? ''}
              onChange={(event) => table.setGlobalFilter(event.target.value)}
              className='h-8 w-full sm:w-[200px] lg:w-[250px]'
              aria-label={searchPlaceholder}
              type='search'
            />
          )}
        </div>

        {/* Filters */}
        {filters.map((filter) => {
          const column = table.getColumn(filter.columnId)
          if (!column) return null
          return (
            <DataTableFacetedFilter
              key={filter.columnId}
              column={column}
              title={filter.title}
              options={filter.options}
            />
          )
        })}

        {/* Additional custom filter components (children) */}
        {children}

        {/* Reset button */}
        {isFiltered && (
          <Button
            variant='ghost'
            onClick={handleReset}
            className='h-8 px-2 lg:px-3'
          >
            Reset
            <Cross2Icon className='ms-2 h-4 w-4' />
          </Button>
        )}
      </div>

      {/* Right side: Actions and view options */}
      <div className='flex items-center gap-2 sm:flex-shrink-0'>
        {actions}
        <DataTableViewOptions table={table} />
      </div>
    </div>
  )
}
