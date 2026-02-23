import type { Block } from '@/types/modele.types';

export function wouldCreateCycle(blocks: Block[], startId: string, targetId: string): boolean {
  const visited = new Set<string>();
  const stack = [startId];
  while (stack.length > 0) {
    const current = stack.pop()!;
    if (current === targetId) return true;
    if (visited.has(current)) continue;
    visited.add(current);
    const block = blocks.find(b => b.id === current);
    if (block) {
      for (const pid of block.parents) {
        stack.push(pid);
      }
    }
  }
  return false;
}

export function isDescendant(blocks: Block[], blockId: string, potentialAncestorId: string, visited: Set<string> = new Set()): boolean {
  if (visited.has(blockId)) return false;
  visited.add(blockId);
  const block = blocks.find(b => b.id === blockId);
  if (!block || block.parents.length === 0) return false;
  if (block.parents.includes(potentialAncestorId)) return true;
  return block.parents.some(pid => isDescendant(blocks, pid, potentialAncestorId, visited));
}

export function getBlockDepth(blocks: Block[], blockId: string, visited: Set<string> = new Set()): number {
  if (visited.has(blockId)) return 0;
  visited.add(blockId);
  const block = blocks.find(b => b.id === blockId);
  if (!block || block.parents.length === 0) return 0;
  return 1 + Math.max(...block.parents.map(pid => getBlockDepth(blocks, pid, new Set(visited))));
}

export function getOrderedBlocks(blocks: Block[]): Block[] {
  const inDegree = new Map<string, number>();
  const children = new Map<string, string[]>();

  for (const b of blocks) {
    inDegree.set(b.id, b.parents.length);
    for (const pid of b.parents) {
      if (!children.has(pid)) children.set(pid, []);
      children.get(pid)!.push(b.id);
    }
  }

  const queue: string[] = [];
  for (const b of blocks) {
    if (b.parents.length === 0) queue.push(b.id);
  }

  const ordered: Block[] = [];
  while (queue.length > 0) {
    const id = queue.shift()!;
    const block = blocks.find(b => b.id === id);
    if (block) ordered.push(block);
    for (const childId of (children.get(id) || [])) {
      const deg = (inDegree.get(childId) || 1) - 1;
      inDegree.set(childId, deg);
      if (deg === 0) queue.push(childId);
    }
  }

  for (const b of blocks) {
    if (!ordered.find(o => o.id === b.id)) ordered.push(b);
  }

  return ordered;
}

export function getBlockDisplayNumber(blocks: Block[], blockId: string): number {
  const ordered = getOrderedBlocks(blocks);
  return ordered.findIndex(b => b.id === blockId) + 1;
}

export function getHierarchicalNumber(
  blocks: Block[],
  blockId: string,
  visiting: Set<string> = new Set(),
): string {
  const block = blocks.find(b => b.id === blockId);
  if (!block) return '';

  // Circular parent chains are now allowed. Fall back to flat numbering.
  if (visiting.has(blockId)) {
    return String(getBlockDisplayNumber(blocks, blockId));
  }
  visiting.add(blockId);

  if (block.parents.length === 0) {
    const roots = blocks.filter(b => b.parents.length === 0);
    const rootIndex = roots.findIndex(b => b.id === blockId);
    visiting.delete(blockId);
    if (rootIndex >= 0) return String(rootIndex + 1);
    return String(getBlockDisplayNumber(blocks, blockId));
  }

  const firstParent = block.parents[0];
  const parentNumber = getHierarchicalNumber(blocks, firstParent, visiting);
  const siblings = blocks.filter(b => b.parents.includes(firstParent));
  const position = siblings.findIndex(b => b.id === blockId) + 1;
  visiting.delete(blockId);

  if (!parentNumber || position <= 0) {
    return String(getBlockDisplayNumber(blocks, blockId));
  }
  return `${parentNumber}.${position}`;
}
