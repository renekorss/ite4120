import React, { useRef, useEffect } from "react";
import { daysLeft } from "./api";
export function Brand() {
  return (
    <span className="brand">
      <i aria-hidden="true" />
      Driving Licence Reminder
    </span>
  );
}

export function Banner({
  children,
  kind = "info",
}: {
  children: React.ReactNode;
  kind?: string;
}) {
  return (
    <div
      className={"banner " + kind}
      role={kind === "error" ? "alert" : "status"}
    >
      <img alt="" src={"/design/" + kind + ".png"} />
      <div>{children}</div>
    </div>
  );
}

export function Sheet({
  label,
  kind,
  children,
  close,
}: {
  label: string;
  kind: string;
  children: React.ReactNode;
  close: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = ref.current;
    el?.showModal();
    return () => el?.close();
  }, []);
  return (
    <dialog
      aria-label={label}
      className={kind}
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          const r = e.currentTarget.getBoundingClientRect();
          if (
            e.clientX < r.left ||
            e.clientX > r.right ||
            e.clientY < r.top ||
            e.clientY > r.bottom
          )
            close();
        }
      }}
    >
      {children}
    </dialog>
  );
}
export function Dialog({
  title,
  children,
  close,
  icon = "info",
  action,
  cancel = "Cancel",
  cancelAction,
  kind = "",
}: {
  title: string;
  children: React.ReactNode;
  close: () => void;
  icon?: string;
  action: React.ReactNode;
  cancel?: string;
  cancelAction?: () => void;
  kind?: string;
}) {
  return (
    <Sheet label={title} kind={"action-sheet " + kind} close={close}>
      <img alt="" className="sheet-icon" src={"/design/" + icon + ".png"} />
      <h2>{title}</h2>
      {children}
      <div className="sheet-actions">
        <button className="secondary" onClick={cancelAction ?? close}>
          {cancel}
        </button>
        {action}
      </div>
    </Sheet>
  );
}
export function DocumentBadge({
  doc,
}: {
  doc?: { status: string; expiresOn: string | null };
}) {
  if (!doc) return null;
  const days = doc.expiresOn ? daysLeft(doc.expiresOn) : Infinity;
  const invalid =
    days < 0 || ["revoked", "suspended", "expired"].includes(doc.status);
  const state = invalid ? "invalid" : days <= 90 ? "at_risk" : doc.status;
  return (
    <Badge
      status={state}
      label={
        invalid
          ? days < 0
            ? "Expired"
            : doc.status
          : days <= 90
            ? "Expires soon"
            : doc.status === "valid"
              ? "Valid"
              : doc.status
      }
    />
  );
}
export function Badge({ status, label }: { status: string; label: string }) {
  return <span className={"badge " + status}>{label}</span>;
}
