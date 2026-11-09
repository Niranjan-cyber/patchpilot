import { motion, type Variants } from "motion/react";

/** One soft spring for everything that moves; MotionConfig reducedMotion="user" (App) drops the travel. */
export const spring = { type: "spring", stiffness: 260, damping: 26 } as const;

const list: Variants = { hide: {}, show: { transition: { staggerChildren: 0.07, delayChildren: 0.04 } } };
const item: Variants = {
  hide: { opacity: 0, y: 18 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] } },
};

/** A block whose direct <Item> children rise in one after another, once. */
export function Stagger({ children, className, as = "div" }: { children: React.ReactNode; className?: string; as?: "div" | "section" | "ul" | "ol" }) {
  const M = motion[as];
  return <M className={className} variants={list} initial="hide" animate="show">{children}</M>;
}
export function Item({ children, className, as = "div", ...rest }: { children: React.ReactNode; className?: string; as?: "div" | "section" | "li" } & Record<string, unknown>) {
  const M = motion[as];
  return <M className={className} variants={item} {...rest}>{children}</M>;
}
