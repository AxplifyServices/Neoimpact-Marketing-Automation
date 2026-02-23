import { Skeleton } from '@/components/ui/skeleton'

interface DataTableSkeletonProps {
  columnCount: number
  rowCount?: number
}

export function DataTableSkeleton({ columnCount, rowCount = 10 }: DataTableSkeletonProps) {
  return (
    <>
      {Array.from({ length: rowCount }).map((_, rowIndex) => (
        <tr key={rowIndex} className='border-b'>
          {Array.from({ length: columnCount }).map((_, cellIndex) => (
            <td key={cellIndex} className='p-4 align-middle'>
              <Skeleton className='h-5 w-full' />
            </td>
          ))}
        </tr>
      ))}
    </>
  )
}
