/** Registry-verified current evidence only; never infer coverage from unsigned files or skill defaults. */
export interface DeviceCell {
 app_version: string; os_version: string; screen: string; density: string; locale: string;
 independent: number; maintainer: number;
 device_labels?: string[];
}
export interface DeviceGrid { cells: DeviceCell[]; independent_cells: number }
export function completeCell(cell: DeviceCell): boolean {
 return [cell.app_version, cell.os_version, cell.screen, cell.density, cell.locale]
  .every((axis) => axis != null && String(axis).trim() !== '' && axis !== '*');
}
