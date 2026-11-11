import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

export const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[var(--radius-md)] font-medium transition-[background-color,color,border-color,box-shadow,transform] duration-150 ease-out active:translate-y-px disabled:opacity-50 disabled:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "bg-accent text-accent-ink shadow-sm hover:bg-accent-hover",
        secondary: "bg-surface text-ink border border-border shadow-sm hover:border-border-strong hover:bg-surface-2",
        ghost: "text-ink-2 hover:text-ink hover:bg-surface-2",
        subtle: "bg-surface-2 text-ink hover:bg-surface-3",
        danger: "bg-danger-soft text-danger-ink hover:bg-danger hover:text-white",
      },
      size: {
        sm: "h-8 px-3 text-sm",
        md: "h-10 px-4 text-sm",
        lg: "h-12 px-5 text-base",
        icon: "size-9",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

type Props = ComponentProps<"button"> & VariantProps<typeof buttonVariants> & { asChild?: boolean };

export function Button({ className, variant, size, asChild, ...props }: Props) {
  const Comp = asChild ? Slot : "button";
  return <Comp className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}
