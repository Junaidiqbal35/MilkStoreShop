import os
import re
from datetime import datetime
import tkinter as tk
from tkinter import messagebox, simpledialog
from sqlalchemy import (
    create_engine, Column, Integer, String, Float,
    ForeignKey, DateTime, inspect, text
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import ttkbootstrap as tb

# ───── Database / ORM Setup ─────
BASE_DIR    = os.path.dirname(__file__)
DB_PATH     = os.path.join(BASE_DIR, 'shop.db')
RECEIPT_DIR = os.path.join(BASE_DIR, 'receipts')
os.makedirs(RECEIPT_DIR, exist_ok=True)

engine  = create_engine(f'sqlite:///{DB_PATH}', echo=False)
Session = sessionmaker(bind=engine)
Base    = declarative_base()

class Product(Base):
    __tablename__ = 'products'
    id             = Column(Integer, primary_key=True)
    name           = Column(String, unique=True, nullable=False)
    price_per_unit = Column(Float, nullable=False)
    stock          = Column(Float, nullable=False)

class Order(Base):
    __tablename__ = 'orders'
    id        = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.now)
    total     = Column(Float, default=0.0)
    items     = relationship('OrderItem', back_populates='order')

class OrderItem(Base):
    __tablename__ = 'order_items'
    id         = Column(Integer, primary_key=True)
    order_id   = Column(Integer, ForeignKey('orders.id'))
    product_id = Column(Integer, ForeignKey('products.id'))
    quantity   = Column(Float, nullable=False)
    line_total = Column(Float, nullable=False)
    order      = relationship('Order', back_populates='items')
    product    = relationship('Product')

# Create tables + migrations
Base.metadata.create_all(engine)
inspector = inspect(engine)
if 'orders' in inspector.get_table_names():
    cols = [c['name'] for c in inspector.get_columns('orders')]
    if 'total' not in cols:
        with engine.connect() as conn:
            conn.execute(text('ALTER TABLE orders ADD COLUMN total FLOAT DEFAULT 0.0'))

# Seed default products
session = Session()
def_products = [
    ("Milk (per kg)",   150.0),
    ("Yogurt (per kg)", 200.0),
    ("Sweets (per dish)",100.0),
    ("Dhai Bhale",      120.0),
    ("Cream Chaat",     130.0),
    ("Rice Pudding",     90.0),
    ("Desi Ghee (250g)",250.0)
]
if session.query(Product).count() == 0:
    for name, price in def_products:
        session.add(Product(name=name, price_per_unit=price, stock=100.0))
    session.commit()

# Receipt utility
def save_receipt(order):
    lines = ["*** MILK SHOP RECEIPT ***",
             f"Order #{order.id}   {order.timestamp:%Y-%m-%d %H:%M:%S}",
             '-'*40]
    for item in order.items:
        lines.append(f"{item.product.name:15s} {item.quantity:>5.2f} × {item.product.price_per_unit:>6.2f} = {item.line_total:>7.2f}")
    lines += ['-'*40, f"TOTAL: {order.total:.2f}", 'Thank you!']
    path = os.path.join(RECEIPT_DIR, f'receipt_{order.id}.txt')
    with open(path, 'w') as f:
        f.write('\n'.join(lines))
    messagebox.showinfo("Receipt", "\n".join(lines))

# Main POS Application with ttkbootstrap
class POSApp(tb.Window):
    def __init__(self):
        super().__init__(themename="superhero", title="Milk Shop POS")
        self.session = session
        self.cart    = {}
        self.cart_keys = []
        # bind Enter for checkout
        self.bind_all('<Return>', lambda e: self._checkout())
        # Build UI
        self._build_ui()

    def _build_ui(self):
        nb = tb.Notebook(self)
        self.prod_frame = tb.Frame(nb)
        self.sale_frame = tb.Frame(nb)
        nb.add(self.prod_frame, text="Products")
        nb.add(self.sale_frame, text="New Sale")
        nb.pack(fill='both', expand=True)
        self._build_products_tab()
        self._build_sale_tab()

    def _build_products_tab(self):
        for w in self.prod_frame.winfo_children(): w.destroy()
        cols = ("ID","Name","Price","Stock")
        self.prod_tree = tb.Treeview(self.prod_frame, columns=cols, show='headings')
        for c in cols: self.prod_tree.heading(c, text=c)
        self.prod_tree.pack(fill='both', expand=True, pady=5)
        for p in self.session.query(Product).order_by(Product.name):
            self.prod_tree.insert('', 'end', values=(p.id, p.name, f"{p.price_per_unit:.2f}", f"{p.stock:.2f}"))
        btns = tb.Frame(self.prod_frame)
        tb.Button(btns, text="Add/Update", bootstyle="success", command=self._add_product).pack(side='left', padx=5)
        tb.Button(btns, text="Delete",     bootstyle="warning", command=self._delete_product).pack(side='left', padx=5)
        tb.Button(btns, text="Refresh",    bootstyle="info",    command=self._build_products_tab).pack(side='left')
        btns.pack(pady=5)

    def _add_product(self):
        name = simpledialog.askstring("Name","Product name:", parent=self)
        if not name: return
        try:
            price = float(simpledialog.askstring("Price","Unit price:", parent=self))
            stock = float(simpledialog.askstring("Stock","Stock qty:", parent=self))
        except:
            messagebox.showerror("Error","Invalid input")
            return
        prod = self.session.query(Product).filter_by(name=name).first()
        if prod:
            prod.price_per_unit, prod.stock = price, stock
        else:
            prod = Product(name=name, price_per_unit=price, stock=stock)
            self.session.add(prod)
        self.session.commit()
        self._build_products_tab()

    def _delete_product(self):
        selected = self.prod_tree.focus()
        if not selected:
            messagebox.showwarning("Warning","No product selected")
            return
        values = self.prod_tree.item(selected, 'values')
        pid = int(values[0])
        prod = self.session.get(Product, pid)
        if messagebox.askyesno("Confirm","Delete product '%s'?" % prod.name):
            self.session.delete(prod)
            self.session.commit()
            self._build_products_tab()

    def _build_sale_tab(self):
        for w in self.sale_frame.winfo_children(): w.destroy()
        btn_frame = tb.Frame(self.sale_frame)
        btn_frame.pack(side='left', fill='y', padx=10, pady=10)
        products = self.session.query(Product).order_by(Product.name).all()
        for idx, p in enumerate(products):
            variants = [(0.5,'½kg'),(1.0,'1kg')] if 'per kg' in p.name else [(1,'')]
            for col,(q,label) in enumerate(variants):
                text = f"{p.name}\n{label or '1'}"
                btn = tb.Button(btn_frame, text=text, width=16, bootstyle="primary",
                                command=lambda p=p,qty=q: self.add_to_cart(p,qty))
                btn.grid(row=idx, column=col, pady=5, padx=5)
        cart_frame = tb.Frame(self.sale_frame)
        cart_frame.pack(side='right', fill='both', expand=True, padx=10, pady=10)
        tb.Label(cart_frame, text='Cart:', font=('Arial',14)).pack(anchor='w')
        self.cart_listbox = tk.Listbox(cart_frame, font=('Arial',12), height=15)
        self.cart_listbox.pack(fill='both', expand=True)
        self.total_lbl = tb.Label(cart_frame, text='Total: 0.00', font=('Arial',14))
        self.total_lbl.pack(anchor='e', pady=5)
        action_frame = tb.Frame(cart_frame)
        tb.Button(action_frame, text='Remove Item', bootstyle='warning', command=self._remove_selected).pack(side='left', padx=5)
        tb.Button(action_frame, text='Clear Cart',  bootstyle='secondary',command=self._clear_cart).pack(side='left', padx=5)
        tb.Button(action_frame, text='Checkout (Enter)', bootstyle='danger', command=self._checkout).pack(side='left', padx=5)
        action_frame.pack(pady=5)

    def add_to_cart(self, product, qty):
        self.cart[product.id] = self.cart.get(product.id, 0) + qty
        self.update_cart_display()

    def update_cart_display(self):
        self.cart_listbox.delete(0, tk.END)
        self.cart_keys = []
        total = 0.0
        for pid, qty in self.cart.items():
            p = self.session.get(Product, pid)
            line = p.price_per_unit * qty
            total += line
            self.cart_listbox.insert(tk.END, f"{p.name}: {qty} x {p.price_per_unit:.2f} = {line:.2f}")
            self.cart_keys.append(pid)
        self.total_lbl.config(text=f"Total: {total:.2f}")

    def _remove_selected(self):
        sel = self.cart_listbox.curselection()
        if not sel:
            messagebox.showwarning("Warning","No item selected to remove")
            return
        idx = sel[0]
        pid = self.cart_keys[idx]
        del self.cart[pid]
        self.update_cart_display()

    def _clear_cart(self):
        if messagebox.askyesno("Confirm","Clear entire cart?"):
            self.cart.clear()
            self.update_cart_display()

    def _checkout(self, event=None):
        if not self.cart:
            messagebox.showinfo("Info","No items selected")
            return
        order = Order()
        self.session.add(order)
        self.session.commit()
        total = 0.0
        for pid, qty in self.cart.items():
            p = self.session.get(Product, pid)
            if p.stock < qty:
                messagebox.showerror("Error",f"Not enough stock for {p.name}")
                return
            line = p.price_per_unit * qty
            total += line
            p.stock -= qty
            item = OrderItem(order_id=order.id, product_id=pid, quantity=qty, line_total=line)
            self.session.add(item)
        order.total = total
        self.session.commit()
        save_receipt(order)
        self.cart.clear()
        self._build_products_tab()
        self.update_cart_display()

if __name__ == '__main__':
    POSApp().mainloop()
