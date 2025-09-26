---
title: "Testdaten sauber erstellen mit dem Fluent Builder Pattern"
date: 2021-05-01T00:00:00+02:00
lastmod: 2021-05-01T00:00:00+02:00
draft: false
author: "Marcel"
description: "Hilfsmethoden erleichtern das Erstellen von Testdaten. Aber mit der Zeit können sie schwer lesbar werden, da man immer mehr Varianten der Testdaten benötigt, um den sich ständig ändernden Anforderungen neuer Tests gerecht zu werden."
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"

tags: ["UnitTest", "C-Sharp", ".Net"]

lightgallery: true
---

Hilfsmethoden erleichtern das Erstellen von Testdaten. Aber mit der Zeit können sie schwer lesbar werden, 
da man immer mehr Varianten der Testdaten benötigt, um den sich ständig weiterentwickelnden Anforderungen neuer Tests gerecht zu werden.

Nehmen wir an, wir haben die folgende `Customer`-Klasse:

```csharp
public class Customer
{
    public string Name { get; set; }
    public DateTime? DateOfBirth { get; set; }
    public string Email { get; set; }
    public string Address { get; set; }
}
```

Normalerweise erstellen wir eine Instanz von `Customer` und setzen die jeweiligen Eigenschaften so:

```csharp
var customer = new Customer();
customer.Name = "Jacob Knight";
customer.DateOfBirth = new DateTime(1988, 5, 1);
customer.Email = "nofec547@anim.com";
customer.Address = "4429 Kelley Road";
```

Der zweite Schritt könnte eine Hilfsmethode sein.  
Diese Hilfsmethode beginnt mit nur einem einzigen Parameter:

```csharp
var customer = NewCustomer("Jacob Knight");
```

Doch schon bald kommen immer mehr Parameter hinzu. Bedingte Abfragen schleichen sich in den `NewCustomer()`-Methodenkörper ein, 
um `null`-Werte zu behandeln, und die Methodenaufrufe werden durch die langen Parameterlisten schwer lesbar:

```csharp
var validDate = NewCustomer("", new DateTime(1988, 5, 1), null, null);
var validEmail = NewCustomer(null, null, "nofec547@anim.com", null);
var validAddress = NewCustomer(null, null, null, "4429 Kelley Road");
```

Oder es wird für jede neue Testanforderung eine zusätzliche Methode geschrieben:

```csharp
var validDate = NewCustomerWithDate("Jacob Knight", new DateTime(1988, 5, 1));
var validEmail = NewCustomerWithEmail("nofec547@anim.com");
var validAddress = NewCustomerWithAddress("4429 Kelley Road");
```

Stattdessen kannst du das **Fluent Builder Pattern** verwenden:  
Du erstellst eine Hilfsklasse, die ein teilweise aufgebautes Objekt zurückgibt, dessen Zustand in Tests überschrieben werden kann.  
Die Hilfsmethode initialisiert logisch erforderliche Felder mit sinnvollen Standardwerten, sodass jeder Test nur die für den Fall relevanten Felder angeben muss:

```csharp
public class CustomerBuilder
{
    private string _name;
    private DateTime? _dateOfBirth;
    private string _email;
    private string _address;

    public CustomerBuilder WithName(string name)
    {
        _name = name;
        return this;
    }

    public CustomerBuilder WithDateOfBirth(DateTime? dateOfBirth)
    {
        _dateOfBirth = dateOfBirth;
        return this;
    }

    public CustomerBuilder WithEmail(string email)
    {
        _email = email;
        return this;
    }

    public CustomerBuilder WithAddress(string address)
    {
        _address = address;
        return this;
    }

    public Customer Build()
    {
        return new Customer()
        {
            Name = _name,
            DateOfBirth = _dateOfBirth,
            Email = _email,
            Address = _address
        };
    }
}
```

Die Nutzung sieht dann so aus:

```csharp
var customer = new CustomerBuilder()
            .WithName("Jacob Knight")
            .WithDateOfBirth(Convert.ToDateTime("01/05/1988"))
            .WithEmail("nofec547@anim.com")
            .WithAddress("4429 Kelley Roa")
            .Build();
```

Mit einem impliziten Operator in der `CustomerBuilder`-Klasse kannst du sogar den `Build()`-Aufruf verstecken:

```csharp
public class CustomerBuilder
{
    //...

    public static implicit operator Customer(CustomerBuilder instance)
    {
        return instance.Build();
    }
}
```

```csharp
Customer implicitCustomer = new CustomerBuilder()
            .WithName("Jacob Knight")
            .WithDateOfBirth(Convert.ToDateTime("01/05/1988"))
            .WithEmail("nofec547@anim.com")
            .WithAddress("4429 Kelley Roa");
```

Ein großer Vorteil ist, dass der Testcode jetzt leichter zu schreiben und zu lesen ist, 
weil die Parameter klar benannt sind.

Beachte außerdem, dass Tests niemals von Standardwerten abhängen sollten, 
die durch eine Hilfsmethode gesetzt werden.  
Das würde Leser zwingen, die Implementierungsdetails der Hilfsmethode zu prüfen, um den Test zu verstehen.

In manchen Fällen haben sich Builder als so nützlich erwiesen, dass sie schließlich auch im Produktionscode verwendet wurden.

Mehr über dieses Thema erfährst du [hier](http://www.natpryce.com/articles/000714.html).
