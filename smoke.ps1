$ErrorActionPreference = "Continue"
$B = "http://localhost:5000/api"
$rand = Get-Random -Minimum 100000 -Maximum 999999
$userEmail = "buyer$rand@example.com"
$pass = "TestPass123!"

function Step($n, $name) { Write-Host ""; Write-Host "=== $n. $name ===" -ForegroundColor Cyan }

Step 1 "HEALTH CHECK"
$h = Invoke-RestMethod -Uri "http://localhost:5000/" -Method Get -TimeoutSec 5
$h | ConvertTo-Json

Step 2 "CATEGORIES"
$cats = Invoke-RestMethod -Uri "$B/categories" -Method Get
$cats | ConvertTo-Json

Step 3 "PRODUCTS (category=Audio, sort=price_asc)"
$prods = Invoke-RestMethod -Uri "$B/products?category=Audio&sort=price_asc" -Method Get
$prods | Select-Object _id, name, category, price, stock | Format-Table -AutoSize

Step 4 "SEARCH ?q=watch"
$search = Invoke-RestMethod -Uri "$B/products?q=watch" -Method Get
$search | Select-Object name, category | Format-Table -AutoSize

Step 5 "REGISTER (signup)"
$signup = Invoke-RestMethod -Uri "$B/auth/signup" -Method Post -ContentType "application/json" -Body (@{ name = "Buyer $rand"; email = $userEmail; password = $pass } | ConvertTo-Json)
$signup | ConvertTo-Json
$token = $signup.token
$uid = $signup.user._id
$hdr = @{ Authorization = "Bearer $token" }
Write-Host "User ID: $uid" -ForegroundColor Yellow

Step 6 "GET /api/auth/me"
$me = Invoke-RestMethod -Uri "$B/auth/me" -Method Get -Headers $hdr
$me | ConvertTo-Json

Step 7 "PRODUCT DETAIL"
$prodId = $prods[0]._id
$detail = Invoke-RestMethod -Uri "$B/products/$prodId" -Method Get
$detail | Select-Object name, price, stock, description | Format-List

Step 8 "ADD TO CART (qty 2, then +1 to same line)"
$add = Invoke-RestMethod -Uri "$B/cart" -Method Post -Headers $hdr -ContentType "application/json" -Body (@{ product_id = $prodId; qty = 2 } | ConvertTo-Json)
$add | Select-Object name, price, qty | Format-Table -AutoSize
$add2 = Invoke-RestMethod -Uri "$B/cart" -Method Post -Headers $hdr -ContentType "application/json" -Body (@{ product_id = $prodId; qty = 1 } | ConvertTo-Json)
$add2 | Select-Object name, price, qty | Format-Table -AutoSize

Step 9 "UPDATE CART QTY to 5"
$upd = Invoke-RestMethod -Uri "$B/cart/$prodId" -Method Patch -Headers $hdr -ContentType "application/json" -Body (@{ qty = 5 } | ConvertTo-Json)
$upd | Select-Object name, price, qty | Format-Table -AutoSize

Step 10 "GET CART"
$cv = Invoke-RestMethod -Uri "$B/cart" -Method Get -Headers $hdr
$cv | Select-Object name, price, qty | Format-Table -AutoSize

Step 11 "CHECKOUT (no payment -> confirmed)"
$order = Invoke-RestMethod -Uri "$B/orders" -Method Post -Headers $hdr -ContentType "application/json" -Body (@{ customer = @{ name = "Buyer $rand"; email = $userEmail; address = "1 Demo St" } } | ConvertTo-Json)
$order | Select-Object _id, status, total, @{n="items";e={($_.items | ForEach-Object { "$($_.name) x$($_.qty)" }) -join ", "}} | Format-List

Step 12 "ORDER HISTORY"
$orders = Invoke-RestMethod -Uri "$B/orders" -Method Get -Headers $hdr
$orders | Select-Object _id, status, total, created_at | Format-Table -AutoSize

Step 13 "CART CLEARED AFTER ORDER"
$empty = Invoke-RestMethod -Uri "$B/cart" -Method Get -Headers $hdr
$empty | ConvertTo-Json

Step 14 "PAID CHECKOUT (Visa 4242)"
$prodId2 = $prods[1]._id
Invoke-RestMethod -Uri "$B/cart" -Method Post -Headers $hdr -ContentType "application/json" -Body (@{ product_id = $prodId2; qty = 1 } | ConvertTo-Json) | Out-Null
$orderPaid = Invoke-RestMethod -Uri "$B/orders" -Method Post -Headers $hdr -ContentType "application/json" -Body (@{
  customer = @{ name = "Buyer $rand"; email = $userEmail; address = "1 Demo St" }
  payment = @{ card_number = "4242424242424242"; card_holder = "Buyer $rand"; exp_month = 12; exp_year = 2099; cvc = "123" }
} | ConvertTo-Json)
$orderPaid | Select-Object _id, status, total, @{n="payment";e={$_.payment | Select-Object brand, last4, exp}} | Format-List

Step 15 "ORDER HISTORY AFTER BOTH"
$orders2 = Invoke-RestMethod -Uri "$B/orders" -Method Get -Headers $hdr
$orders2 | Select-Object _id, status, total, created_at | Format-Table -AutoSize

Write-Host ""; Write-Host "===== BUYER E2E OK =====" -ForegroundColor Green
