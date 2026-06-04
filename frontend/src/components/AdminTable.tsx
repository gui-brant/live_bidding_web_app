import type { ReactNode } from "react";
import { cloneElement, isValidElement } from "react";

export type ColumnDef = {
  key: string;
  header: ReactNode;
  width: string;
  align?: "left" | "center" | "right";
  className?: string;
};

type AdminTableProps<T> = {
  columns: ColumnDef[];
  rows: T[];
  rowKey: (row: T) => string;
  renderRow: (row: T) => ReactNode[];
  emptyStateText?: string;
};

const alignClass = (align?: ColumnDef["align"]) => {
  if (align === "right") {
    return "admin-align-right";
  }
  if (align === "center") {
    return "admin-align-center";
  }
  return "";
};

const AdminTable = <T,>({ columns, rows, rowKey, renderRow, emptyStateText }: AdminTableProps<T>) => {
  return (
    <div className="table-scroll">
      <table className="admin-table">
        <colgroup>
          {columns.map((column) => (
            <col key={column.key} style={{ width: column.width }} />
          ))}
        </colgroup>
        <thead>
          <tr>
            {columns.map((column) => {
              const classes = [column.className, alignClass(column.align)].filter(Boolean).join(" ");
              return (
                <th key={column.key} className={classes}>
                  {column.header}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const cells = renderRow(row);
            return (
              <tr key={rowKey(row)}>
                {columns.map((column, index) => {
                  const cell = cells[index];
                  const classes = [column.className, alignClass(column.align)].filter(Boolean).join(" ");
                  if (isValidElement(cell) && cell.type === "td") {
                    const existing = (cell.props as { className?: string }).className ?? "";
                    const merged = [existing, classes].filter(Boolean).join(" ");
                    return cloneElement(cell, { key: column.key, className: merged });
                  }
                  return (
                    <td key={column.key} className={classes}>
                      {cell}
                    </td>
                  );
                })}
              </tr>
            );
          })}
          {!rows.length ? (
            <tr>
              <td colSpan={columns.length} className="muted admin-empty">
                {emptyStateText ?? "No data available."}
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
};

export default AdminTable;

