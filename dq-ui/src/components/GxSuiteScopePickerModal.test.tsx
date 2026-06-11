/** @vitest-environment jsdom */

import React from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { GxSuiteScopePickerModal } from './GxSuiteScopePickerModal'

const mockReset = vi.fn()
const mockSelectProduct = vi.fn()
const mockSelectDataset = vi.fn()
const mockSelectDataObject = vi.fn()
const mockSelectVersion = vi.fn()
const mockLoadDatasets = vi.fn()
const mockLoadDataObjects = vi.fn()
const mockLoadVersions = vi.fn()
const mockLoadAttributes = vi.fn()
let mockFilteredProducts: any[] = [
  {
    id: 'product-1',
    name: 'Sales Product',
    workspaceId: 'ws-1',
    icon: 'database',
    tags: ['customer', 'pii'],
    datasets: [],
  },
]

vi.mock('../contexts/DataProductContext', () => ({
  useDataProduct: () => ({
    state: {
      selectedProduct: { id: 'product-1', name: 'Sales Product', workspaceId: 'ws-1' },
      selectedDataset: null,
      selectedDataObject: null,
      selectedVersion: null,
    },
    reset: mockReset,
    selectProduct: mockSelectProduct,
    selectDataset: mockSelectDataset,
    selectDataObject: mockSelectDataObject,
    selectVersion: mockSelectVersion,
    filteredProducts: mockFilteredProducts,
    standaloneDatasets: [],
    loadDatasets: mockLoadDatasets,
    loadDataObjects: mockLoadDataObjects,
    loadVersions: mockLoadVersions,
    loadAttributes: mockLoadAttributes,
    isLoadingDatasets: () => false,
    isLoadingObjects: () => false,
    isLoadingVersions: () => false,
    isLoadingAttributes: () => false,
  }),
}))

vi.mock('./HierarchyTree', () => ({
  HierarchyTreePanel: ({ children, title, countLabel }: any) => (
    <section>
      <h2>{title}</h2>
      <span>{countLabel}</span>
      {children}
    </section>
  ),
  HierarchyTreeRow: ({ label, onSelect }: any) => (
    <button type="button" onClick={onSelect}>{label}</button>
  ),
  HierarchyTreeStatus: ({ label }: any) => <div>{label}</div>,
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  mockFilteredProducts = [
    {
      id: 'product-1',
      name: 'Sales Product',
      workspaceId: 'ws-1',
      icon: 'database',
      tags: ['customer', 'pii'],
      datasets: [],
    },
  ]
})

describe('GxSuiteScopePickerModal', () => {
  it('confirms the selected data product through the shared modal shell', () => {
    const onClose = vi.fn()
    const onSelect = vi.fn()

    render(
      <GxSuiteScopePickerModal
        isOpen={true}
        onClose={onClose}
        onSelect={onSelect}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Sales Product' }))
    fireEvent.click(screen.getByRole('button', { name: 'Select' }))

    expect(onSelect).toHaveBeenCalledWith({
      kind: 'data_product',
      dataProductId: 'product-1',
      dataProductName: 'Sales Product',
      workspaceId: 'ws-1',
      tagIds: [],
    })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('adds an existing local tag from the catalog metadata', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    const onSelect = vi.fn()

    render(
      <GxSuiteScopePickerModal
        isOpen={true}
        onClose={onClose}
        onSelect={onSelect}
      />,
    )

    await user.click(screen.getByLabelText('Execution tags'))
    await user.type(screen.getByLabelText('Execution tags'), 'pi')
    await user.click(screen.getByRole('button', { name: 'pii' }))
    fireEvent.click(screen.getByRole('button', { name: 'Sales Product' }))
    fireEvent.click(screen.getByRole('button', { name: 'Select' }))

    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({
      kind: 'data_product',
      dataProductId: 'product-1',
      dataProductName: 'Sales Product',
      workspaceId: 'ws-1',
      tagIds: ['pii'],
    }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('creates a new tag inline when no catalog tag matches', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    const onSelect = vi.fn()

    render(
      <GxSuiteScopePickerModal
        isOpen={true}
        onClose={onClose}
        onSelect={onSelect}
      />,
    )

    await user.click(screen.getByLabelText('Execution tags'))
    await user.type(screen.getByLabelText('Execution tags'), 'fraud')
    await user.keyboard('{Enter}')
    fireEvent.click(screen.getByRole('button', { name: 'Sales Product' }))
    fireEvent.click(screen.getByRole('button', { name: 'Select' }))

    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({
      kind: 'data_product',
      dataProductId: 'product-1',
      dataProductName: 'Sales Product',
      workspaceId: 'ws-1',
      tagIds: ['fraud'],
    }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})