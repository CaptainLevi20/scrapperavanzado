import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { KeyRound } from "lucide-react";
import { changePassword } from "../../api/auth";
import { ApiError } from "../../api/client";
import { Button } from "../ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "../ui/dialog";
import { Input } from "../ui/input";
import { Label } from "../ui/label";

interface ChangePasswordDialogProps {
  collapsed?: boolean;
}

export function ChangePasswordDialog({ collapsed = false }: ChangePasswordDialogProps) {
  const [open, setOpen] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const mutation = useMutation({
    mutationFn: () => changePassword(currentPassword, newPassword),
    onSuccess: () => {
      setSuccess(true);
      setError(null);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    },
    onError: (err: unknown) => {
      setError(err instanceof ApiError ? err.message : "No se pudo cambiar la contraseña");
      setSuccess(false);
    },
  });

  function handleSubmit() {
    setError(null);
    setSuccess(false);
    if (newPassword !== confirmPassword) {
      setError("Las contraseñas no coinciden");
      return;
    }
    mutation.mutate();
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        setOpen(nextOpen);
        if (nextOpen) {
          setCurrentPassword("");
          setNewPassword("");
          setConfirmPassword("");
          setError(null);
          setSuccess(false);
        }
      }}
    >
      <DialogTrigger asChild>
        <button
          title={collapsed ? "Cambiar contraseña" : undefined}
          className={`flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium text-sidebar-foreground/60 transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground ${
            collapsed ? "justify-center" : ""
          }`}
        >
          <KeyRound className="size-4 shrink-0" aria-hidden="true" />
          {!collapsed && "Cambiar contraseña"}
        </button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-display">Cambiar contraseña</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="change-password-current">Contraseña actual</Label>
            <Input
              id="change-password-current"
              type="password"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="change-password-new">Nueva contraseña</Label>
            <Input
              id="change-password-new"
              type="password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              minLength={8}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="change-password-confirm">Confirmar nueva contraseña</Label>
            <Input
              id="change-password-confirm"
              type="password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
            />
          </div>
          {error && <p className="text-sm font-medium text-rojo">{error}</p>}
          {success && <p className="text-sm font-medium text-verde">Contraseña actualizada.</p>}
        </div>
        <DialogFooter>
          <Button onClick={handleSubmit} disabled={mutation.isPending}>
            {mutation.isPending ? "Guardando…" : "Guardar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
